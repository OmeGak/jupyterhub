"""Test a proxy being started before the Hub"""

import json
import os
from queue import Queue
from subprocess import Popen

from .. import orm
from .mocking import MockHub
from .test_api import api_request
from ..utils import wait_for_http_server

def test_external_proxy(request, io_loop):
    """Test a proxy started before the Hub"""
    auth_token='secret!'
    proxy_ip = '127.0.0.1'
    proxy_port = 54321
    
    app = MockHub.instance(
        proxy_api_ip=proxy_ip,
        proxy_api_port=proxy_port,
        proxy_auth_token=auth_token,
    )
    def fin():
        MockHub.clear_instance()
        app.stop()
    request.addfinalizer(fin)
    env = os.environ.copy()
    env['CONFIGPROXY_AUTH_TOKEN'] = auth_token
    cmd = app.proxy_cmd + [
        '--ip', app.ip,
        '--port', str(app.port),
        '--api-ip', proxy_ip,
        '--api-port', str(proxy_port),
        '--default-target', 'http://%s:%i' % (app.hub_ip, app.hub_port),
    ]
    proxy = Popen(cmd, env=env)
    def _cleanup_proxy():
        if proxy.poll() is None:
            proxy.terminate()
    request.addfinalizer(_cleanup_proxy)
    
    def wait_for_proxy():
        io_loop.run_sync(lambda : wait_for_http_server(
            'http://%s:%i' % (proxy_ip, proxy_port)))
    wait_for_proxy()
    
    app.start([])
    
    assert app.proxy_process is None
    
    routes = io_loop.run_sync(app.proxy.get_routes)
    assert list(routes.keys()) == ['/']
    
    # add user
    name = 'river'
    r = api_request(app, 'users', name, method='post')
    r.raise_for_status()
    r = api_request(app, 'users', name, 'server', method='post')
    r.raise_for_status()
    
    routes = io_loop.run_sync(app.proxy.get_routes)
    assert sorted(routes.keys()) == ['/', '/user/river']
    
    # teardown the proxy and start a new one in the same place
    proxy.terminate()
    proxy = Popen(cmd, env=env)
    wait_for_proxy()
    
    routes = io_loop.run_sync(app.proxy.get_routes)
    assert list(routes.keys()) == ['/']
    
    # poke the server to update the proxy
    r = api_request(app, 'proxy', method='post')
    r.raise_for_status()
    
    # check that the routes are correct
    routes = io_loop.run_sync(app.proxy.get_routes)
    assert sorted(routes.keys()) == ['/', '/user/river']
    
    # teardown the proxy again, and start a new one with different auth and port
    proxy.terminate()
    new_auth_token = 'different!'
    env['CONFIGPROXY_AUTH_TOKEN'] = new_auth_token
    proxy_port = 55432
    cmd = app.proxy_cmd + [
        '--ip', app.ip,
        '--port', str(app.port),
        '--api-ip', app.proxy_api_ip,
        '--api-port', str(proxy_port),
        '--default-target', 'http://%s:%i' % (app.hub_ip, app.hub_port),
    ]
    
    proxy = Popen(cmd, env=env)
    wait_for_proxy()
    
    # tell the hub where the new proxy is
    r = api_request(app, 'proxy', method='patch', data=json.dumps({
        'port': proxy_port,
        'auth_token': new_auth_token,
    }))
    r.raise_for_status()
    assert app.proxy.api_server.port == proxy_port
    
    # get updated auth token from main thread
    def get_app_proxy_token():
        q = Queue()
        app.io_loop.add_callback(lambda : q.put(app.proxy.auth_token))
        return q.get(timeout=2)
        
    assert get_app_proxy_token() == new_auth_token
    app.proxy.auth_token = new_auth_token
    
    # check that the routes are correct
    routes = io_loop.run_sync(app.proxy.get_routes)
    assert sorted(routes.keys()) == ['/', '/user/river']

def test_check_routes(app, io_loop):
    proxy = app.proxy
    r = api_request(app, 'users/zoe', method='post')
    r.raise_for_status()
    r = api_request(app, 'users/zoe/server', method='post')
    r.raise_for_status()
    zoe = orm.User.find(app.db, 'zoe')
    assert zoe is not None
    before = sorted(io_loop.run_sync(app.proxy.get_routes))
    assert '/user/zoe' in before
    io_loop.run_sync(app.proxy.check_routes)
    io_loop.run_sync(lambda : proxy.delete_user(zoe))
    during = sorted(io_loop.run_sync(app.proxy.get_routes))
    assert '/user/zoe' not in during
    io_loop.run_sync(app.proxy.check_routes)
    after = sorted(io_loop.run_sync(app.proxy.get_routes))
    assert '/user/zoe' in after
    assert before == after
