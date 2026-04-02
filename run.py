import os

if os.environ.get('SOCKETIO_ASYNC_MODE', 'eventlet').strip().lower() == 'eventlet':
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
