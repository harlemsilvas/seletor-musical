import React, {useId, useState} from 'react';
import {matchArtists, MIN_ARTIST_CHARS} from './tracks';
// Campo com busca incremental: sugestões a partir do 3º caractere (combobox acessível por teclado).
export default function ArtistPicker({artists, value, onChange}) {
 const id = useId();
 const [text, setText] = useState(''), [open, setOpen] = useState(false), [active, setActive] = useState(0);
 const query = value ? '' : text;
 const options = matchArtists(artists, query);
 const shown = open && !value;
 function choose(item) { onChange(item.artist); setText(''); setOpen(false); setActive(0); }
 function clear() { onChange(''); setText(''); setOpen(false); }
 function key(e) {
  if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive(i => Math.min(i + 1, options.length - 1)); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(i => Math.max(i - 1, 0)); }
  else if (e.key === 'Enter' && shown && options[active]) { e.preventDefault(); choose(options[active]); }
  else if (e.key === 'Escape') { setOpen(false); if (value) clear(); }
 }
 const typed = text.trim().length;
 return <div className="artist-picker">
  <label htmlFor={id}>Artista</label>
  <div className="picker-field">
   <input id={id} role="combobox" aria-expanded={shown && options.length > 0} aria-controls={`${id}-list`} aria-autocomplete="list"
    aria-activedescendant={shown && options[active] ? `${id}-${active}` : undefined} autoComplete="off" aria-label="Filtrar por artista"
    value={value || text} readOnly={!!value} placeholder={`Digite ${MIN_ARTIST_CHARS}+ letras…`}
    onChange={e => { setText(e.target.value); setOpen(true); setActive(0); }} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onKeyDown={key}/>
   {value && <button type="button" className="secondary" aria-label="Limpar filtro de artista" onClick={clear}>×</button>}
  </div>
  {shown && typed > 0 && typed < MIN_ARTIST_CHARS && <small className="muted">Digite pelo menos {MIN_ARTIST_CHARS} letras.</small>}
  {shown && typed >= MIN_ARTIST_CHARS && !options.length && <small className="muted">Nenhum artista encontrado.</small>}
  {shown && options.length > 0 && <ul id={`${id}-list`} role="listbox" aria-label="Artistas encontrados">
   {options.map((item, i) => <li key={item.artist} id={`${id}-${i}`} role="option" aria-selected={i === active} className={i === active ? 'active' : ''}
    onMouseDown={e => { e.preventDefault(); choose(item); }} onMouseEnter={() => setActive(i)}>{item.artist} <small>({item.count})</small></li>)}
  </ul>}
 </div>;
}
