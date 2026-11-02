"""Servidor de teste em 8767, apenas com áudio sintético em pasta temporária."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import subprocess
import tempfile

import uvicorn
from backend.app import app, ORIGINS
from backend.downloads import DownloadManager
from backend.library import Library

@asynccontextmanager
async def fixture_lifespan(app):
    with tempfile.TemporaryDirectory(prefix='seletor-library-test-') as root:
        root=Path(root)
        manager=DownloadManager(root/'data',root/'music')
        manager.download_dir.mkdir()
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=12','-metadata','title=Áudio de teste local','-metadata','artist=Artista de teste','-c:a','libmp3lame',str(manager.download_dir/'fixture.mp3')],check=True)
        await manager.start()
        library=Library(manager)
        await library.start()
        manager.on_completed=library.request_refresh
        app.state.downloads=manager;app.state.library=library
        try:
            yield
        finally:
            await library.close()
            await manager.close()

if __name__=='__main__':
    ORIGINS.add('http://localhost:8767')
    app.router.lifespan_context=fixture_lifespan
    uvicorn.run(app,host='127.0.0.1',port=8767,access_log=False)
