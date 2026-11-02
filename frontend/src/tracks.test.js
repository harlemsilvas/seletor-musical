import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseTracks, filterTracks, selectedUrls, videoUrl, groupByArtist, matchArtists} from './tracks.js';
const url='https://www.youtube.com/watch?v=D0_GWTy9FEM';
test('JSONL, playlist JSON, plain text, canonical links and deduplication',()=>{
 const raw=JSON.stringify({id:'D0_GWTy9FEM',title:'Faixa',channel:'Canal'})+'\nNome | https://youtu.be/D0_GWTy9FEM?list=RDtest\nOutra | https://youtu.be/abcdefghijk';
 const items=parseTracks(raw);assert.equal(items.length,2);assert.equal(items[0].url,url);
 assert.equal(parseTracks(JSON.stringify({entries:[{id:'D0_GWTy9FEM'}]})).length,1);
 assert.equal(parseTracks('invalid\n{"entries":[null]}').length,0);
 assert.equal(videoUrl('https://youtube.com.evil/watch?v=D0_GWTy9FEM'),null);
});
test('filter by title/channel, selection preserved outside filter, selected copy',()=>{
 const items=parseTracks(JSON.stringify([{id:'D0_GWTy9FEM',title:'Faixa',channel:'Canal'},{id:'abcdefghijk',title:'Outra'}]));
 assert.equal(filterTracks(items,'CANAL').length,1);assert.equal(filterTracks(items,'outra').length,1);
 const selected=new Set(filterTracks(items,'canal').map(t=>t.id));assert.equal(selectedUrls(items,selected),url);
 selected.add('abcdefghijk');assert.equal(selectedUrls(items,selected).split('\n').length,2);
});
test('agrupa por artista principal sem diferenciar maiúsculas e nomeia faixas sem artista',()=>{
 const groups=groupByArtist([{id:1,artist_primary:'P!NK'},{id:3,artist_primary:'Sia'},{id:2,artist_primary:'P!nk'},{id:4,artist_primary:''}]);
 assert.deepEqual(groups.map(g=>[g.name,g.items.length]),[['P!NK',2],['Sia',1],['Artista desconhecido',1]]);
});
test('busca de artista só a partir do 3º caractere, sem acentos e com prefixo primeiro',()=>{
 const artists=[{artist:'Calvin Harris',count:4},{artist:'Ariana Grande',count:5},{artist:'Marina',count:1},{artist:'Zé Ramalho',count:2},{artist:'Sia',count:3}];
 assert.deepEqual(matchArtists(artists,'ar'),[]);
 assert.deepEqual(matchArtists(artists,'  ar '),[]);
 assert.deepEqual(matchArtists(artists,'ari').map(a=>a.artist),['Ariana Grande','Marina']);
 assert.deepEqual(matchArtists(artists,'ZE R').map(a=>a.artist),['Zé Ramalho']);
 assert.deepEqual(matchArtists(artists,'xyz'),[]);
 assert.equal(matchArtists(Array.from({length:30},(_,i)=>({artist:`Banda ${i}`,count:1})),'ban').length,10);
});
