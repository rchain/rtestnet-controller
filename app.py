import asyncio
import logging
from pathlib import Path
from pprint import pprint

from quart import Quart, request, jsonify, send_from_directory

import lib_app_config
import lib_net_ctx

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)8s %(name)s %(message)s'
)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app_config = lib_app_config.AppConfig(
    {
        'data_dir': './data',
        'gcp_credentials_file': './tomassvc.google-service-account.json',
        'initial_delay': 10,
        'check_interval': 10,
    }
)
net_ctx = lib_net_ctx.NetworkContext(app_config)

app = Quart(__name__)


@app.before_serving
async def init():
    asyncio.create_task(net_ctx.run())


@app.route('/nodes/<node_name>', methods=['PUT'])
async def api_node_put(node_name):
    config = await request.get_json()
    if node in net_ctx.nodes:
        node = net_ctx.nodes[node_name]
    else:
        net_ctx.create_node(node_name, config)
    return '', 200


@app.route('/heartbeat/<node_name>', methods=['POST'])
async def api_heartbeat(node_name):
    try:
        msg = await request.get_json()
        reply = net_ctx.nodes[node_name].heartbeat(msg or {})
        return jsonify(reply)
    except KeyError:
        return '', 404

@app.route('/files/<node_name>/<path:filename>', methods=['GET'])
async def api_files(node_name, filename):
    root = Path(app_config.nodes_data_dir) / node_name / 'files'
    return await send_from_directory(root, filename)
