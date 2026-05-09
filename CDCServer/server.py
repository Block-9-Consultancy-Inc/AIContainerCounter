# --- Running the App (for development) ---
# You would typically run this using Uvicorn:
# uvicorn main:app --reload

if __name__ == '__main__':
    import uvicorn
    # Load environment variables from .env file
    from os import environ
    from dotenv import load_dotenv
    load_dotenv()

    uvicorn.run(
        'server.app:app',
        host=environ.get('HOST', '0.0.0.0'),
        port=int(environ.get('PORT', '8000')),
        reload=environ.get('PYTHON_ENV', 'DEVELOPMENT') != 'PRODUCTION'
    )