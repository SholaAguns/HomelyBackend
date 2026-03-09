
# Police and crime data

- Endpoint: `https://data.police.uk/api/`
- Requires no auth
- Documentation: https://data.police.uk/docs/
- Endpoint of interest: https://data.police.uk/api/crimes-at-location?date=2024-01&location_id=1738423
## API call limits
The Police API call limit operates using a 'leaky bucket' algorithm as a controller. This allows for infrequent bursts of calls, and allows you to continue to make an unlimited amount of calls over time.

The current rate limit is **15 requests per second with a burst of 30**. So, on average you must make fewer than 15 requests each second, but you can make up to 30 in a single second.
## All crime categories
[{"url":"all-crime","name":"All crime"},{"url":"anti-social-behaviour","name":"Anti-social behaviour"},{"url":"bicycle-theft","name":"Bicycle theft"},{"url":"burglary","name":"Burglary"},{"url":"criminal-damage-arson","name":"Criminal damage and arson"},{"url":"drugs","name":"Drugs"},{"url":"other-theft","name":"Other theft"},{"url":"possession-of-weapons","name":"Possession of weapons"},{"url":"public-order","name":"Public order"},{"url":"robbery","name":"Robbery"},{"url":"shoplifting","name":"Shoplifting"},{"url":"theft-from-the-person","name":"Theft from the person"},{"url":"vehicle-crime","name":"Vehicle crime"},{"url":"violent-crime","name":"Violence and sexual offences"},{"url":"other-crime","name":"Other crime"}]