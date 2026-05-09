# --- Running the App (for development) ---
# You would typically run this using Uvicorn:
# uvicorn main:app --reload

if __name__ == '__main__':
    import uvicorn

    uvicorn.run('server.app:app', host='0.0.0.0', port=8000, reload=True)