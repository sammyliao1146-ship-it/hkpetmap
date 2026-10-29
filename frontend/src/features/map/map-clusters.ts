import type {PetPlace} from '../../api/client';

export function clusterPlaces(places:PetPlace[], zoom:number, contains:(lat:number,lon:number)=>boolean, activeId?:string, enabled=true) {
  const active=places.find(p=>p.id===activeId);
  const individuals:PetPlace[]=[];
  const cells=new Map<string,PetPlace[]>();
  const scale=256*2**zoom;
  for(const p of places){
    if(p.latitude==null||p.longitude==null)continue;
    const selected=active && p.latitude===active.latitude && p.longitude===active.longitude;
    if(!selected&&!contains(p.latitude,p.longitude))continue;
    if(!enabled||zoom>=15||selected){individuals.push(p);continue;}
    const sine=Math.sin(Math.max(-85,Math.min(85,p.latitude))*Math.PI/180);
    const x=(p.longitude+180)/360*scale;
    const y=(.5-Math.log((1+sine)/(1-sine))/(4*Math.PI))*scale;
    const key=`${Math.floor(x/64)}:${Math.floor(y/64)}`;
    cells.set(key,[...(cells.get(key)||[]),p]);
  }
  const clusters:{key:string;latitude:number;longitude:number;count:number}[]=[];
  for(const [key,items] of cells){
    if(items.length===1){individuals.push(items[0]);continue;}
    clusters.push({key,latitude:items.reduce((n,p)=>n+p.latitude!,0)/items.length,
      longitude:items.reduce((n,p)=>n+p.longitude!,0)/items.length,count:items.length});
  }
  return {individuals,clusters};
}
