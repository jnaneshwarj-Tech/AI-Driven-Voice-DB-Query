/**
 * Builds the translation tables from the base strings plus every section file
 * dropped into ./sections.
 *
 * Sections are named `<area>.en.js` / `<area>.kn.js` and default-export a flat
 * key → string map. They are loaded with import.meta.glob so adding a section
 * is a single new file — no shared file has to be edited, which keeps two
 * people (or two agents) working on different screens from touching the same
 * module.
 *
 * Lookup order is base → section, and LanguageContext falls back from Kannada
 * to English per key, so an untranslated string shows English rather than a
 * raw `nav.query`.
 */
import enBase from './en';
import knBase from './kn';

const enSections = import.meta.glob('./sections/*.en.js', { eager: true });
const knSections = import.meta.glob('./sections/*.kn.js', { eager: true });

const merge = (mods) => Object.assign({}, ...Object.values(mods).map((m) => m.default));

export const dictionaries = {
  en: { ...enBase, ...merge(enSections) },
  kn: { ...knBase, ...merge(knSections) },
};

export default dictionaries;
