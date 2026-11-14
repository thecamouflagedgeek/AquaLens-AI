/* Paste into the Earth Engine Code Editor. Draw a polygon wholly within a
 * sufficiently wide reach, rename the import geometry, then run the task. */
var reach = geometry;
var start = '2019-01-01';
var end = '2026-01-01';
var station = 'Replace with the reach name';
var collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(reach).filterDate(start, end)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60));
var rows = ee.FeatureCollection(collection.map(function(image) {
  var water = image.select('SCL').eq(6);
  var rgb = image.select(['B2', 'B3', 'B4'], ['blue', 'green', 'red'])
    .multiply(0.0001).updateMask(water);
  var means = rgb.reduceRegion({reducer: ee.Reducer.mean(), geometry: reach, scale: 20, maxPixels: 1e7});
  var count = rgb.select('blue').reduceRegion({reducer: ee.Reducer.count(), geometry: reach, scale: 20, maxPixels: 1e7});
  return ee.Feature(null, means).set({
    water_pixels: count.get('blue'), scene_id: image.get('system:index'),
    captured: image.date().format("yyyy-MM-dd'T'HH:mm:ss'Z'", 'UTC'),
    utc_day: image.date().format('yyyy-MM-dd', 'UTC'), reach: station, source: 'COPERNICUS/S2_SR_HARMONIZED'
  });
})).filter(ee.Filter.notNull(['blue', 'green', 'red', 'water_pixels']))
  .filter(ee.Filter.gte('water_pixels', 10)).sort('captured').distinct(['utc_day']);
Map.centerObject(reach, 12);
Map.addLayer(reach, {}, 'Analysis reach');
Export.table.toDrive({collection: rows, description: 'aqualens_sentinel2', fileFormat: 'GeoJSON'});

