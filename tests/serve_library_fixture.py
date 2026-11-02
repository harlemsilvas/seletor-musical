"""Servidor de teste em 8767, apenas com áudio sintético em pasta temporária."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import subprocess
import tempfile

import uvicorn
from backend.app import app, ORIGINS
from backend.downloads import DownloadManager
from backend.enrich import Enricher
from backend.library import Library

@asynccontextmanager
async def fixture_lifespan(app):
    with tempfile.TemporaryDirectory(prefix='seletor-library-test-') as root:
        root=Path(root)
        manager=DownloadManager(root/'data',root/'music')
        manager.download_dir.mkdir()
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=12','-metadata','title=Áudio de teste local','-metadata','artist=Artista de teste','-c:a','libmp3lame',str(manager.download_dir/'fixture.mp3')],check=True)
        for name,title,artist in (('b1.mp3','Faixa Beta Um','Banda Beta'),('b2.mp3','Faixa Beta Dois','banda beta')):
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=330:duration=2','-metadata',f'title={title}','-metadata',f'artist={artist}','-c:a','libmp3lame',str(manager.download_dir/name)],check=True)
        await manager.start()
        # Faixa com metadados e capa locais (como depois de um download ou do enriquecimento).
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=550:duration=2','-c:a','libmp3lame',str(manager.download_dir/'Faixa-Com-Capa_ccccccccccc.mp3')],check=True)
        manager.covers_dir.mkdir()
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=320x180:rate=1','-frames:v','1',str(manager.covers_dir/'ccccccccccc.jpg')],check=True)
        with manager._connect() as conn:
            conn.execute("INSERT INTO video_meta(video_id,artist,artist_primary,track,release_date,upload_date,source,has_cover) VALUES('ccccccccccc','Cantor Capa','Cantor Capa','Faixa Com Capa','','20170816','title',1)")
        library=Library(manager)
        await library.start()
        manager.on_completed=library.request_refresh
        enricher=Enricher(manager,library)
        app.state.downloads=manager;app.state.library=library;app.state.enrich=enricher
        try:
            yield
        finally:
            await enricher.close()
            await library.close()
            await manager.close()

if __name__=='__main__':
    ORIGINS.add('http://localhost:8767')
    app.router.lifespan_context=fixture_lifespan
    uvicorn.run(app,host='127.0.0.1',port=8767,access_log=False)
