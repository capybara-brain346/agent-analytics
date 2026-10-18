# site_config

One YAML for each site in `config/sites/<site_id>.yaml`.

`load_site_config` → `SiteConfig`: sources, ingest token hash, CDN bucket, key pages, journeys, access policy.
`SiteNotFound` if the file is missing. The site list = the files in the folder.
