# Configuration file for jupyterhub.

import os

c = get_config()

# spawn with custom docker containers
c.JupyterHub.spawner_class = 'dockerspawner.CustomDockerSpawner'

# The docker instances need access to the Hub, so the default loopback port doesn't work:
from IPython.utils.localinterfaces import public_ips
c.JupyterHub.hub_ip = public_ips()[0]

# OAuth with GitHub
c.JupyterHub.authenticator_class = 'oauthenticator.GitHubOAuthenticator'
c.GitHubOAuthenticator.oauth_callback_url = os.environ['OAUTH_CALLBACK_URL']

# boot2docker hax
c.Spawner.tls = True
c.Spawner.debug = True
c.Spawner.http_timeout = 32
c.Spawner.container_ip = '192.168.59.103'
