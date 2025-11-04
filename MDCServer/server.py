from aiohttp import web
import argparse
import logging
import ssl
import os
from dotenv import load_dotenv
from prisma import Prisma, models, enums
import asyncio

load_dotenv(dotenv_path="./.env")

db = None

default_headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': '*',
    'Access-Control-Allow-Headers': '*',
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Expose-Headers': '*',
    'Access-Control-Max-Age': '86400'
}

ROOT = os.path.dirname(__file__)

IMAGES_DIR = os.getenv('IMAGES_DIR')
print(f'images dir: {IMAGES_DIR}')

def cond_dict(
        cond: bool, cond_dict: dict,
) -> dict:
    return cond_dict if cond else {}

def dict_not_none(
        val, cond_dict: dict,
) -> dict:
    return cond_dict if val != None else {}

async def cors_manual(request):
    print(request)
    return web.Response(
            headers=default_headers
        )

async def init_db():
    print('initializing db')
    global db
    try:
        db = Prisma(auto_register=True)
        await db.connect()
        print('successfully initialized db!')
    except Exception as e:
        print('unable to initialize db ' + str(e))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI Counting Machine MCD Server"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8081, help="Port for HTTP server (default: 8081)"
    )
    parser.add_argument("--record-to", help="Write received media to a file.")
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application(client_max_size=1024**3)
    if os.getenv('PYTHON_ENV') != 'production':
        app.router.add_static('/images', 'images', show_index=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    web.run_app(
        app,
        access_log=None,
        host=args.host,
        port=args.port,
        ssl_context=ssl_context,
        loop=loop
    )