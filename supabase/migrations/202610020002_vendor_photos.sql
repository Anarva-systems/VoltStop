alter table public.vendors
  add column if not exists image_url text;

alter table public.vendors
  add constraint vendors_image_url_http_check
  check (image_url is null or image_url ~ '^https?://');
