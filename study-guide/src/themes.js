'use strict';
// 16 soft pastel themes. Each theme is a single accent colour; the stylesheet
// derives backgrounds, surfaces and text tints from it with color-mix(), so a
// custom colour works exactly like a preset.
const THEMES = [
  { id: 'rose', name: 'Rose', color: '#F4C2C2' },
  { id: 'blush', name: 'Blush', color: '#F9D5E5' },
  { id: 'peach', name: 'Peach', color: '#FFD3B6' },
  { id: 'apricot', name: 'Apricot', color: '#FDE2B8' },
  { id: 'butter', name: 'Butter', color: '#FFF0A8' },
  { id: 'pistachio', name: 'Pistachio', color: '#D6EDBE' },
  { id: 'mint', name: 'Mint', color: '#BFEBD6' },
  { id: 'seafoam', name: 'Seafoam', color: '#B5E5DC' },
  { id: 'aqua', name: 'Aqua', color: '#B8E6EC' },
  { id: 'sky', name: 'Sky', color: '#BFDCF7' },
  { id: 'periwinkle', name: 'Periwinkle', color: '#C9CFF7' },
  { id: 'lavender', name: 'Lavender', color: '#D8C9F3' },
  { id: 'lilac', name: 'Lilac', color: '#E7CBEF' },
  { id: 'mauve', name: 'Mauve', color: '#E3C6D6' },
  { id: 'sand', name: 'Sand', color: '#E8DCC8' },
  { id: 'cloud', name: 'Cloud', color: '#D9E0E8' },
];

const HEX = /^#[0-9a-fA-F]{6}$/;

function themeColor(user) {
  if (!user) return THEMES.find((t) => t.id === 'periwinkle').color;
  if (user.theme === 'custom' && HEX.test(user.custom_color || '')) return user.custom_color;
  const t = THEMES.find((x) => x.id === user.theme);
  return (t || THEMES[10]).color;
}

module.exports = { THEMES, themeColor, HEX };
