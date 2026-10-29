import test from 'node:test';
import assert from 'node:assert/strict';
import {clusterPlaces} from '../src/features/map/map-clusters.ts';

const places=Array.from({length:100},(_,i)=>({id:'p'+i,latitude:22.3+i*.00001,longitude:114.17}));

test('overview aggregates counts; close zoom retains every visible place',()=>{
  const low=clusterPlaces(places,11,()=>true);
  assert(low.clusters.length<10);
  assert.equal(low.individuals.length+low.clusters.reduce((n,c)=>n+c.count,0),100);
  const high=clusterPlaces(places,15,()=>true);
  assert.equal(high.individuals.length,100);assert.equal(high.clusters.length,0);
});

test('viewport culling retains a selected offscreen place and its colocated venues',()=>{
  const same={id:'same',latitude:places[0].latitude,longitude:places[0].longitude};
  const data=clusterPlaces([...places,same],11,()=>false,'p0');
  assert.deepEqual(data.individuals.map(p=>p.id),['p0','same']);
  assert.equal(data.clusters.length,0);
  assert.equal(clusterPlaces(places,11,()=>false).individuals.length,0);
});

test('plan mode avoids clusters and missing coordinates never create pins',()=>{
  const data=clusterPlaces([...places,{id:'unknown',latitude:null,longitude:null}],11,()=>true,undefined,false);
  assert.equal(data.individuals.length,100);assert.equal(data.clusters.length,0);
});
