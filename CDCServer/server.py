# --- Running the App (for development) ---
# You would typically run this using Uvicorn:
# uvicorn main:app --reload

if __name__ == '__main__':
    import uvicorn
    # Load environment variables from .env file
    from os import environ, makedirs
    from dotenv import load_dotenv
    load_dotenv()

    makedirs(environ.get('TEMP_DATA_DIR', './temp_data_dir'), exist_ok=True)
    
    uvicorn.run(
        'server.app:app',
        host=environ.get('HOST', '0.0.0.0'),
        port=int(environ.get('PORT', '8000')),
        reload=environ.get('PYTHON_ENV', 'DEVELOPMENT') != 'PRODUCTION',
        timeout_keep_alive=300
    )