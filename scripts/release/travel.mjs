/** Structural validation only: never official timetable/metric acceptance. */
export function validateTravelDataset({gemeinden,destinations,access,meta,matrices}){
 if(!meta||meta.fixture===true||(Object.hasOwn(meta,'fixture')&&typeof meta.fixture!=='boolean'))throw new Error('Synthetic or invalid fixture metadata cannot be published.');
 const date=typeof meta.referenceDate==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(meta.referenceDate)?new Date(`${meta.referenceDate}T00:00:00Z`):null;
 if(!date||!Number.isFinite(date.getTime())||date.toISOString().slice(0,10)!==meta.referenceDate||date.getUTCDay()!==2)throw new Error('Travel reference date must be a valid Tuesday.');
 if(meta.window!=='06:30-08:30')throw new Error('Travel window must be 06:30-08:30.');
 if(typeof meta.timetable!=='string'||!meta.timetable.trim())throw new Error('Travel timetable label is missing.');
 const homes=Object.keys(gemeinden).sort(),keys=Object.keys(access?.gemeinden??{}).sort();
 if(!homes.length||JSON.stringify(homes)!==JSON.stringify(keys))throw new Error('Travel access must cover every residential origin, without extras.');
 for(const id of homes){const stop=access.gemeinden[id];if(stop!==null&&(!Array.isArray(stop)||stop.length!==3||typeof stop[0]!=='string'||!stop[0].trim()||typeof stop[1]!=='string'||!stop[1].trim()||!Number.isInteger(stop[2])||stop[2]<0||stop[2]>60))throw new Error(`Invalid origin access: ${id}.`);}
 const expected=destinations.filter(id=>access.gemeinden[id]!==null).map(String).sort();
 if(JSON.stringify(expected)!==JSON.stringify(Object.keys(matrices).sort()))throw new Error('A destination capital matrix is missing or unexpected.');
 for(const id of expected){
  const matrix=matrices[id];if(matrix?.to!==Number(id)||!Array.isArray(matrix.rows)||!matrix.rows.some(row=>row[0]===Number(id)&&row[1]===0))throw new Error(`Invalid destination capital matrix: ${id}.`);
  const seen=new Set();let previous=null;
  for(const row of matrix.rows){
   if(!Array.isArray(row)||row.length!==2||!Number.isInteger(row[0])||!Object.hasOwn(gemeinden,String(row[0]))||!access.gemeinden[row[0]]||!Number.isInteger(row[1])||row[1]<0||row[1]>60||seen.has(row[0]))throw new Error(`Invalid travel row for ${id}.`);
   if(previous&&(row[1]<previous[1]||(row[1]===previous[1]&&row[0]<=previous[0])))throw new Error(`Travel rows must be sorted by minutes then BFS: ${id}.`);
   if(row[1]===0&&access.gemeinden[row[0]][0]!==access.gemeinden[id][0])throw new Error(`False zero travel time: ${row[0]} to ${id}.`);
   seen.add(row[0]);previous=row;
  }
 }
 return true;
}
