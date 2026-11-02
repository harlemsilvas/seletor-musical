export function videoUrl(raw) {
  try {
    const u = new URL(raw);
    if (!['http:', 'https:'].includes(u.protocol)) return null;
    let id;
    if (u.hostname === 'youtu.be') id = u.pathname.slice(1);
    else if (['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'].includes(u.hostname))
      id = u.searchParams.get('v') || u.pathname.match(/^\/(?:shorts|embed|live)\/([^/]+)$/)?.[1];
    return /^[\w-]{11}$/.test(id || '') ? `https://www.youtube.com/watch?v=${id}` : null;
  } catch { return null; }
}
export function parseTracks(text) {
  const items = [], seen = new Set();
  function add(o) {
    if (Array.isArray(o)) return o.forEach(add);
    if (!o || typeof o !== 'object') return;
    if (Array.isArray(o.entries)) return o.entries.forEach(add);
    const url = videoUrl(o.webpage_url || o.url || `https://youtu.be/${o.id}`);
    if (!url || seen.has(url)) return;
    seen.add(url);
    const id = new URL(url).searchParams.get('v');
    items.push({id, url, title: typeof o.title === 'string' && o.title.trim() ? o.title : `Vídeo ${id}`, channel: typeof (o.channel || o.uploader) === 'string' ? (o.channel || o.uploader) : '', duration: Number.isFinite(o.duration) && o.duration >= 0 ? o.duration : null, thumbnail: typeof o.thumbnail === 'string' ? o.thumbnail : (Array.isArray(o.thumbnails) ? o.thumbnails.at(-1)?.url : null)});
  }
  try { add(JSON.parse(text)); } catch {
    for (const line of text.split(/\r?\n/)) {
      try { add(JSON.parse(line)); } catch {
        const url = line.match(/https?:\/\/[^\s|<>"']+/)?.[0];
        if (url) add({url, title: line.replace(url, '').replace(/^[\s\d.\-]+/, '').replace(/[|\t\s-]+$/, '')});
      }
    }
  }
  return items;
}
export const filterTracks = (items, term) => items.filter(t => `${t.title} ${t.channel}`.toLocaleLowerCase().includes(term.toLocaleLowerCase()));
export const selectedUrls = (items, selected) => items.filter(t => selected.has(t.id)).map(t => t.url).join('\n');
