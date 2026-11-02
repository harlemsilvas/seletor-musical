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
export function groupByArtist(items) {
  // Agrupa pelo artista principal sem diferenciar maiúsculas, mesmo que a lista ainda não esteja ordenada por artista.
  const groups = new Map();
  for (const item of items) {
    const name = item.artist_primary || 'Artista desconhecido';
    const key = name.toLocaleLowerCase();
    if (!groups.has(key)) groups.set(key, {name, items: []});
    groups.get(key).items.push(item);
  }
  return [...groups.values()];
}

const fold = text => text.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase();
export const MIN_ARTIST_CHARS = 3;
export function matchArtists(artists, query, limit = 10) {
  // A partir do 3º caractere, sem diferenciar acentos/maiúsculas; começa-com vem antes de contém.
  const q = fold(query.trim());
  if (q.length < MIN_ARTIST_CHARS) return [];
  const starts = [], contains = [];
  for (const item of artists) {
    const name = fold(item.artist);
    if (name.startsWith(q)) starts.push(item);
    else if (name.includes(q)) contains.push(item);
  }
  return [...starts, ...contains].slice(0, limit);
}
