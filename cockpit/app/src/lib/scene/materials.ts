/* ====== MATERIAL FACTORY -- 5-tone palette system for 3D shapes ======
   Ported from client/js/scene/render.js material system.
   Each group gets a MatFactory with dark/mid/light/accent/screen tones. */

import * as THREE from "three";

export interface Palette {
  d: number; // dark hex int
  m: number; // mid hex int
  l: number; // light hex int
  a: number; // accent hex int
}

export interface MatFactory {
  dark: () => THREE.MeshStandardMaterial;
  mid: () => THREE.MeshStandardMaterial;
  light: () => THREE.MeshStandardMaterial;
  accent: () => THREE.MeshStandardMaterial;
  screen: () => THREE.MeshStandardMaterial;
  palette: Palette;
}

export function createMatFactory(
  groupColorInt: number,
  envMap?: THREE.Texture | null,
): MatFactory {
  // Derive 5 tones from the group color
  const baseColor = new THREE.Color(groupColorInt);
  const hsl = { h: 0, s: 0, l: 0 };
  baseColor.getHSL(hsl);

  const darkColor = new THREE.Color().setHSL(hsl.h, hsl.s * 0.6, hsl.l * 0.4);
  const midColor = new THREE.Color().setHSL(hsl.h, hsl.s * 0.8, hsl.l * 0.7);
  const lightColor = new THREE.Color().setHSL(hsl.h, hsl.s * 0.5, Math.min(hsl.l * 1.3, 0.85));
  const accentColor = new THREE.Color().setHSL(hsl.h, Math.min(hsl.s * 1.2, 1.0), hsl.l * 0.9);
  const screenColor = new THREE.Color().setHSL(hsl.h, hsl.s * 0.3, 0.08);

  const palette: Palette = {
    d: darkColor.getHex(),
    m: midColor.getHex(),
    l: lightColor.getHex(),
    a: accentColor.getHex(),
  };

  const base = {
    roughness: 0.55,
    metalness: 0.15,
    envMap: envMap ?? undefined,
    envMapIntensity: envMap ? 0.3 : 0,
  };

  // Cache materials — shapes call these factories many times per node.
  // Without caching, 100 nodes × ~10 calls each = 1000+ material objects.
  let _dark: THREE.MeshStandardMaterial | null = null;
  let _mid: THREE.MeshStandardMaterial | null = null;
  let _light: THREE.MeshStandardMaterial | null = null;
  let _accent: THREE.MeshStandardMaterial | null = null;
  let _screen: THREE.MeshStandardMaterial | null = null;

  return {
    dark: () =>
      (_dark ??= new THREE.MeshStandardMaterial({
        ...base,
        color: darkColor.clone(),
        roughness: 0.7,
      })),
    mid: () =>
      (_mid ??= new THREE.MeshStandardMaterial({
        ...base,
        color: midColor.clone(),
      })),
    light: () =>
      (_light ??= new THREE.MeshStandardMaterial({
        ...base,
        color: lightColor.clone(),
        roughness: 0.35,
        metalness: 0.25,
      })),
    accent: () =>
      (_accent ??= new THREE.MeshStandardMaterial({
        ...base,
        color: accentColor.clone(),
        emissive: accentColor.clone(),
        emissiveIntensity: 0.08,
      })),
    screen: () =>
      (_screen ??= new THREE.MeshStandardMaterial({
        ...base,
        color: screenColor.clone(),
        roughness: 0.2,
        metalness: 0.05,
        emissive: screenColor.clone(),
        emissiveIntensity: 0.15,
      })),
    palette,
  };
}

// Default gray factory for nodes without a group color
const DEFAULT_COLOR = 0x556677;

export function createDefaultMatFactory(
  envMap?: THREE.Texture | null,
): MatFactory {
  return createMatFactory(DEFAULT_COLOR, envMap);
}
