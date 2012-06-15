# -*- coding: utf-8 -
#
# This file is part of gunicorn released under the MIT license.
# See the NOTICE for more information.
#

from datetime import datetime
import errno
import os
import select
import socket

import gunicorn.http as http
import gunicorn.http.wsgi as wsgi
import gunicorn.util as util
import gunicorn.workers.base as base

class SyncWorker(base.Worker):
    def run(self):
        # We use a blocking accept() for this so that the worker properly
        # enters a sleep state and is only woken up once there is a connection
        # that has been handed to that worker. This prevents expensive racing
        # for accept between multiple processes as seen in a select-accept loop
        # on multi-core systems with a large number of worker processes (>32)
        self.socket.setblocking(1)

        while self.alive:
            try:
                self.enter_safe_sleep()
                client, addr = self.socket.accept()
                self.notify()

                client.setblocking(1)
                util.close_on_exec(client)

                self.handle(client, addr)

                # Keep processing clients until no one is waiting. This
                # prevents the need to getppid() for every client that we
                # process.
                continue

            except socket.error, e:
                if e[0] not in (errno.EAGAIN, errno.ECONNABORTED):
                    raise
            finally:
                # Prevents us from getting into a perpetual safe-sleep state
                self.notify()

            # If our parent changed then we shut down.
            if self.ppid != os.getppid():
                self.log.info("Parent changed, shutting down: %s", self)
                return

    def handle(self, client, addr):
        req = None
        try:
            parser = http.RequestParser(self.cfg, client)
            req = parser.next()
            self.handle_request(req, client, addr)
        except StopIteration, e:
            self.log.debug("Closing connection. %s", e)
        except socket.error, e:
            if e[0] != errno.EPIPE:
                self.log.exception("Error processing request.")
            else:
                self.log.debug("Ignoring EPIPE")
        except Exception, e:
            self.handle_error(req, client, addr, e)
        finally:
            util.close(client)

    def handle_request(self, req, client, addr):
        environ = {}
        try:
            self.cfg.pre_request(self, req)
            request_start = datetime.now()
            resp, environ = wsgi.create(req, client, addr,
                    self.address, self.cfg)
            # Force the connection closed until someone shows
            # a buffering proxy that supports Keep-Alive to
            # the backend.
            resp.force_close()
            self.nr += 1
            if self.nr >= self.max_requests:
                self.log.info("Autorestarting worker after current request.")
                self.alive = False
            respiter = self.wsgi(environ, resp.start_response)
            try:
                if isinstance(respiter, environ['wsgi.file_wrapper']):
                    resp.write_file(respiter)
                else:
                    for item in respiter:
                        resp.write(item)
                resp.close()
                request_time = datetime.now() - request_start
                self.log.access(resp, req, environ, request_time)
            finally:
                if hasattr(respiter, "close"):
                    respiter.close()
        except socket.error:
            raise
        except Exception, e:
            # Only send back traceback in HTTP in debug mode.
            self.handle_error(req, client, addr, e)
            return
        finally:
            try:
                self.cfg.post_request(self, req, environ)
            except:
                pass

