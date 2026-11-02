import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseTracks, filterTracks, selectedUrls, videoUrl} from './tracks.js';
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
