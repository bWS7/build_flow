import os
import platform


def _resolve_local_async_mode() -> str:
    configured = os.environ.get('SOCKETIO_ASYNC_MODE', '').strip().lower()
    if configured in {'eventlet', 'threading'}:
        return configured
    # On Windows/dev, prefer threading to avoid eventlet monkey-patch issues.
    if platform.system().lower().startswith('win'):
        return 'threading'
    return 'eventlet'


ASYNC_MODE = _resolve_local_async_mode()
os.environ['SOCKETIO_ASYNC_MODE'] = ASYNC_MODE

if ASYNC_MODE == 'eventlet':
    import eventlet

    eventlet.monkey_patch()

from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=False,
        allow_unsafe_werkzeug=True,
    )
