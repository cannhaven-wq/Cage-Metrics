// Slug helper. Lowercase, drop apostrophes, replace any non-alphanumeric run
// with a single hyphen, trim. Returns 'item' as a fallback so we never emit
// empty filenames.
function slugify(s) {
  return String(s ?? '')
    .toLowerCase()
    .replace(/'/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'item';
}

module.exports = { slugify };
