// shapes.js -- Shape builder module extracted from engineering-brain-map prototype.
// Exports mkObj(shape, size, matFactory) that creates 3D groups for 25+ shapes.

import * as T from 'three';
import { ParametricGeometry } from 'three/addons/geometries/ParametricGeometry.js';

/**
 * Build a Three.js Group that represents the given shape.
 *
 * @param {string}  shape      - One of the 26 recognized shape names.
 * @param {number}  size       - Base size scalar (all geometry is proportional to this).
 * @param {object}  matFactory - Object with material factory methods:
 *                                 dark()   -> MeshStandardMaterial (darkest tone)
 *                                 mid()    -> MeshStandardMaterial (mid tone)
 *                                 light()  -> MeshStandardMaterial (lightest tone)
 *                                 accent() -> MeshStandardMaterial (accent colour)
 *                                 screen() -> MeshStandardMaterial (dark screen surface)
 *                               Each call may return a cached material -- the caller owns
 *                               the caching policy.  The factory also exposes a `palette`
 *                               property  { d, m, l, a }  with raw hex colour values so
 *                               that one-off MeshPhysicalMaterial instances (brain crystal)
 *                               can reference the current palette.
 * @returns {T.Group}
 */
export function mkObj(shape, size, matFactory) {
  const s   = size;
  const g   = new T.Group();

  // Convenience aliases matching the prototype's M_DARK / M_MID / etc.
  const M_DARK   = () => matFactory.dark();
  const M_MID    = () => matFactory.mid();
  const M_LIGHT  = () => matFactory.light();
  const M_ACCENT = () => matFactory.accent();
  const M_SCREEN = () => matFactory.screen();
  const _pal     = matFactory.palette;   // { d, m, l, a } hex numbers

  switch (shape) {

  // ── warehouse ───────────────────────────────────────────────────────
  // Seed files -- filing cabinet with organized drawers
  case 'warehouse': {
    const cab = new T.Mesh(new T.BoxGeometry(s * .55, s * .7, s * .45), M_DARK());
    g.add(cab);
    // 4 drawer fronts
    for (let i = 0; i < 4; i++) {
      const dr = new T.Mesh(new T.BoxGeometry(s * .48, s * .12, s * .02), M_MID());
      dr.position.set(0, s * .22 - i * s * .16, s * .235);
      g.add(dr);
      // Drawer handle
      const hdl = new T.Mesh(new T.BoxGeometry(s * .15, s * .02, s * .03), M_LIGHT());
      hdl.position.set(0, s * .22 - i * s * .16, s * .26);
      g.add(hdl);
    }
    // Top surface with label plate
    const top = new T.Mesh(new T.BoxGeometry(s * .58, s * .03, s * .48), M_ACCENT());
    top.position.y = s * .365;
    g.add(top);
    break;
  }

  // ── factory ─────────────────────────────────────────────────────────
  // Code mining -- drill rig extracting from code
  case 'factory': {
    // Base platform
    const base = new T.Mesh(new T.BoxGeometry(s * .6, s * .1, s * .5), M_DARK());
    base.position.y = -s * .15;
    g.add(base);
    // Derrick tower
    const tower = new T.Mesh(new T.BoxGeometry(s * .08, s * .6, s * .08), M_MID());
    tower.position.set(s * .1, s * .15, 0);
    g.add(tower);
    const cross1 = new T.Mesh(new T.BoxGeometry(s * .25, s * .03, s * .03), M_ACCENT());
    cross1.position.set(s * .1, s * .35, 0);
    g.add(cross1);
    const cross2 = new T.Mesh(new T.BoxGeometry(s * .2, s * .03, s * .03), M_ACCENT());
    cross2.position.set(s * .1, s * .15, 0);
    g.add(cross2);
    // Drill bit
    const drill = new T.Mesh(new T.ConeGeometry(s * .04, s * .18, 8), M_LIGHT());
    drill.position.set(s * .1, -s * .18, 0);
    drill.rotation.x = Math.PI;
    g.add(drill);
    // Drill pipe
    const pipe = new T.Mesh(new T.CylinderGeometry(s * .015, s * .015, s * .25, 8), M_ACCENT());
    pipe.position.set(s * .1, -s * .02, 0);
    g.add(pipe);
    // Control box
    const ctrl2 = new T.Mesh(new T.BoxGeometry(s * .2, s * .2, s * .18), M_DARK());
    ctrl2.position.set(-s * .18, s * .0, 0);
    g.add(ctrl2);
    const screen = new T.Mesh(new T.PlaneGeometry(s * .14, s * .1), M_SCREEN());
    screen.position.set(-s * .18, s * .04, s * .1);
    g.add(screen);
    break;
  }

  // ── satellite ───────────────────────────────────────────────────────
  // Ontologies -- satellite dish on pedestal
  case 'satellite': {
    const pole = new T.Mesh(new T.CylinderGeometry(s * .06, s * .1, s * .5, 8), M_DARK());
    g.add(pole);
    const dish = new T.Mesh(
      new T.SphereGeometry(s * .32, 16, 12, 0, Math.PI * 2, 0, Math.PI * .45), M_MID());
    dish.rotation.x = Math.PI * .2;
    dish.position.y = s * .3;
    g.add(dish);
    const feed = new T.Mesh(new T.CylinderGeometry(s * .015, s * .015, s * .4, 8), M_ACCENT());
    feed.position.set(0, s * .45, -s * .1);
    feed.rotation.x = .3;
    g.add(feed);
    const tip = new T.Mesh(new T.SphereGeometry(s * .04, 8, 8), M_LIGHT());
    tip.position.set(0, s * .62, -s * .2);
    g.add(tip);
    break;
  }

  // ── terminal ────────────────────────────────────────────────────────
  // Obs log -- open ledger with log entries
  case 'terminal': {
    // Book base (thick open book)
    const spine = new T.Mesh(new T.BoxGeometry(s * .08, s * .08, s * .45), M_DARK());
    g.add(spine);
    const pageL = new T.Mesh(new T.BoxGeometry(s * .32, s * .04, s * .42), M_MID());
    pageL.position.set(-s * .19, s * .02, 0);
    pageL.rotation.z = .08;
    g.add(pageL);
    const pageR = new T.Mesh(new T.BoxGeometry(s * .32, s * .04, s * .42), M_MID());
    pageR.position.set(s * .19, s * .02, 0);
    pageR.rotation.z = -.08;
    g.add(pageR);
    // Log lines on pages
    for (let i = 0; i < 5; i++) {
      const w = s * (.12 + Math.random() * .1);
      const lineL = new T.Mesh(new T.BoxGeometry(w, s * .008, s * .01), M_ACCENT());
      lineL.position.set(-s * .2 + s * .02, s * .05, -s * .12 + i * s * .07);
      g.add(lineL);
      const lineR = new T.Mesh(new T.BoxGeometry(w, s * .008, s * .01), M_ACCENT());
      lineR.position.set(s * .2 - s * .02, s * .05, -s * .12 + i * s * .07);
      g.add(lineR);
    }
    // Pen/stylus
    const pen = new T.Mesh(new T.CylinderGeometry(s * .01, s * .008, s * .25, 8), M_LIGHT());
    pen.position.set(s * .3, s * .08, s * .1);
    pen.rotation.z = -.3;
    pen.rotation.x = .2;
    g.add(pen);
    break;
  }

  // ── monument ────────────────────────────────────────────────────────
  // L0 Axioms -- stepped monumental pyramid, 4 tiers
  case 'monument': {
    for (let i = 0; i < 4; i++) {
      const w = s * (.7 - i * .14), h = s * .14;
      const tier = new T.Mesh(new T.BoxGeometry(w, h, w), i < 2 ? M_DARK() : M_MID());
      tier.position.y = i * s * .15;
      g.add(tier);
    }
    // Capstone
    const cap = new T.Mesh(new T.ConeGeometry(s * .12, s * .15, 4), M_LIGHT());
    cap.position.y = s * .65;
    cap.rotation.y = Math.PI / 4;
    g.add(cap);
    break;
  }

  // ── pillars ─────────────────────────────────────────────────────────
  // L1 Principles -- classical columns with entablature
  case 'pillars': {
    const base2 = new T.Mesh(new T.BoxGeometry(s * .8, s * .06, s * .35), M_DARK());
    base2.position.y = -s * .18;
    g.add(base2);
    for (let i = 0; i < 3; i++) {
      const col = new T.Mesh(new T.CylinderGeometry(s * .045, s * .055, s * .45, 8), M_MID());
      col.position.set((i - 1) * s * .28, s * .05, 0);
      g.add(col);
    }
    const entab = new T.Mesh(new T.BoxGeometry(s * .85, s * .07, s * .38), M_LIGHT());
    entab.position.y = s * .31;
    g.add(entab);
    const ped = new T.Mesh(new T.ConeGeometry(s * .42, s * .12, 3), M_ACCENT());
    ped.position.y = s * .42;
    g.add(ped);
    break;
  }

  // ── gear ────────────────────────────────────────────────────────────
  // L2 Patterns -- interlocking gears
  case 'gear': {
    const g1 = new T.Mesh(new T.TorusGeometry(s * .28, s * .08, 8, 20), M_MID());
    g1.rotation.x = Math.PI / 2;
    g1.userData.animate = 'gear_main';
    g.add(g1);
    const g2 = new T.Mesh(new T.TorusGeometry(s * .18, s * .06, 8, 16), M_DARK());
    g2.rotation.x = Math.PI / 2;
    g2.position.set(s * .3, s * .05, 0);
    g2.userData.animate = 'gear_secondary';
    g.add(g2);
    const axle = new T.Mesh(new T.CylinderGeometry(s * .04, s * .04, s * .2, 8), M_ACCENT());
    g.add(axle);
    const axle2 = new T.Mesh(new T.CylinderGeometry(s * .03, s * .03, s * .15, 8), M_ACCENT());
    axle2.position.set(s * .3, s * .05, 0);
    g.add(axle2);
    break;
  }

  // ── gate ────────────────────────────────────────────────────────────
  // L3 Rules -- padlock (constraints)
  case 'gate': {
    // Lock body
    const body = new T.Mesh(new T.BoxGeometry(s * .45, s * .35, s * .2), M_DARK());
    body.position.y = -s * .08;
    g.add(body);
    // Rounded top of lock body
    const topR = new T.Mesh(
      new T.CylinderGeometry(s * .225, s * .225, s * .2, 16, 1, false, 0, Math.PI), M_DARK());
    topR.rotation.z = Math.PI / 2;
    topR.rotation.y = Math.PI / 2;
    topR.position.y = s * .1;
    g.add(topR);
    // Shackle (U-shape)
    const shackle = new T.Mesh(new T.TorusGeometry(s * .15, s * .03, 8, 16, Math.PI), M_LIGHT());
    shackle.position.y = s * .22;
    g.add(shackle);
    // Shackle legs
    const legL = new T.Mesh(new T.CylinderGeometry(s * .03, s * .03, s * .12, 8), M_LIGHT());
    legL.position.set(-s * .15, s * .16, 0);
    g.add(legL);
    const legR = new T.Mesh(new T.CylinderGeometry(s * .03, s * .03, s * .12, 8), M_LIGHT());
    legR.position.set(s * .15, s * .16, 0);
    g.add(legR);
    // Keyhole
    const keyH = new T.Mesh(new T.CylinderGeometry(s * .035, s * .035, s * .02, 8), M_SCREEN());
    keyH.position.set(0, -s * .1, s * .11);
    keyH.rotation.x = Math.PI / 2;
    g.add(keyH);
    const keySlit = new T.Mesh(new T.BoxGeometry(s * .02, s * .06, s * .02), M_SCREEN());
    keySlit.position.set(0, -s * .14, s * .11);
    g.add(keySlit);
    break;
  }

  // ── database ────────────────────────────────────────────────────────
  // L4 Evidence -- stacked DB cylinders
  case 'database': {
    for (let i = 0; i < 3; i++) {
      const c = new T.Mesh(
        new T.CylinderGeometry(s * .3, s * .3, s * .12, 12), i === 1 ? M_MID() : M_DARK());
      c.position.y = i * s * .16 - s * .1;
      g.add(c);
    }
    break;
  }

  // ── hourglass ───────────────────────────────────────────────────────
  // L5 Context -- refined hourglass with frame
  case 'hourglass': {
    // Frame pillars
    for (const dx of [-1, 1]) {
      const p = new T.Mesh(new T.CylinderGeometry(s * .02, s * .02, s * .65, 8), M_ACCENT());
      p.position.x = dx * s * .22;
      g.add(p);
    }
    // Top and bottom caps
    const topCap = new T.Mesh(new T.CylinderGeometry(s * .24, s * .24, s * .03, 8), M_LIGHT());
    topCap.position.y = s * .32;
    g.add(topCap);
    const botCap = new T.Mesh(new T.CylinderGeometry(s * .24, s * .24, s * .03, 8), M_LIGHT());
    botCap.position.y = -s * .32;
    g.add(botCap);
    // Glass bulbs
    const topBulb = new T.Mesh(new T.ConeGeometry(s * .2, s * .28, 8), M_MID());
    topBulb.position.y = s * .14;
    topBulb.rotation.x = Math.PI;
    g.add(topBulb);
    const botBulb = new T.Mesh(new T.ConeGeometry(s * .2, s * .28, 8), M_DARK());
    botBulb.position.y = -s * .14;
    g.add(botBulb);
    // Neck
    const neck = new T.Mesh(new T.CylinderGeometry(s * .03, s * .03, s * .08, 8), M_ACCENT());
    neck.userData.animate = 'hg_neck';
    g.add(neck);
    break;
  }

  // ── brain ───────────────────────────────────────────────────────────
  // ERG -- solid amethyst crystal with Mobius ring
  case 'brain': {
    // Gem core -- LatheGeometry brilliant-cut silhouette, solid from palette
    const gemPts = [
      new T.Vector2(0, s * .22),
      new T.Vector2(s * .16, s * .06),
      new T.Vector2(s * .20, 0),
      new T.Vector2(s * .12, -s * .10),
      new T.Vector2(0, -s * .18),
    ];
    const gemGeo = new T.LatheGeometry(gemPts, 16);
    const crystal = new T.Mesh(gemGeo, new T.MeshStandardMaterial({
      color: _pal.m, metalness: .30, roughness: .15,
      emissive: new T.Color(_pal.a), emissiveIntensity: .08
    }));
    g.add(crystal);
    // Inner core -- subtle glow catches bloom
    const core = new T.Mesh(
      new T.IcosahedronGeometry(s * .08, 1),
      new T.MeshStandardMaterial({
        color: _pal.l, metalness: .25, roughness: .45,
        emissive: new T.Color(_pal.a), emissiveIntensity: .2
      }));
    g.add(core);
    // Mobius strip -- solid from palette
    const R = s * .38, Wb = s * .07;
    const mFn = (u, t, tgt) => {
      u *= Math.PI * 2;
      t = t * 2 - 1;
      tgt.set(
        (R + Wb * t * Math.cos(u / 2)) * Math.cos(u),
        Wb * t * Math.sin(u / 2),
        (R + Wb * t * Math.cos(u / 2)) * Math.sin(u)
      );
    };
    const mGeo = new ParametricGeometry(mFn, 48, 6);
    const strip = new T.Mesh(mGeo, new T.MeshStandardMaterial({
      color: _pal.d, metalness: .30, roughness: .55, side: T.DoubleSide
    }));
    strip.rotation.z = Math.PI * .06;
    g.add(strip);
    break;
  }

  // ── dyson_book ──────────────────────────────────────────────────────
  // Knowledge Library -- open book with curved pages + pedestal + Dyson sphere
  case 'dyson_book': {
    // Pedestal base
    const pedGeo = new T.CylinderGeometry(s * .22, s * .26, s * .08, 16);
    const pedMat = M_DARK();
    g.add(new T.Mesh(pedGeo, pedMat));
    const pedRim = new T.Mesh(new T.TorusGeometry(s * .24, s * .012, 8, 20), M_MID());
    pedRim.rotation.x = Math.PI / 2;
    pedRim.position.y = s * .04;
    g.add(pedRim);
    // Book spine (thinner, above pedestal)
    const spine = new T.Mesh(new T.BoxGeometry(s * .05, s * .4, s * .32), M_DARK());
    spine.position.y = s * .08;
    g.add(spine);
    // Left page -- extruded with page curl deformation
    const pgMat = M_LIGHT();
    const pgLGeo = new T.BoxGeometry(s * .26, s * .38, s * .015, 8, 1, 1);
    const pgLPos = pgLGeo.attributes.position;
    for (let vi = 0; vi < pgLPos.count; vi++) {
      const px = pgLPos.getX(vi);
      const curl = Math.sin((-px / (s * .26) + 0.5) * Math.PI * .4) * s * .015;
      pgLPos.setZ(vi, pgLPos.getZ(vi) + curl);
    }
    pgLGeo.computeVertexNormals();
    const pageL = new T.Mesh(pgLGeo, pgMat);
    pageL.position.set(-s * .16, s * .08, 0);
    pageL.rotation.y = Math.PI * 0.06;
    g.add(pageL);
    // Right page -- mirrored curl
    const pgRGeo = new T.BoxGeometry(s * .26, s * .38, s * .015, 8, 1, 1);
    const pgRPos = pgRGeo.attributes.position;
    for (let vi = 0; vi < pgRPos.count; vi++) {
      const px = pgRPos.getX(vi);
      const curl = Math.sin((px / (s * .26) + 0.5) * Math.PI * .4) * s * .015;
      pgRPos.setZ(vi, pgRPos.getZ(vi) + curl);
    }
    pgRGeo.computeVertexNormals();
    const pageR = new T.Mesh(pgRGeo, pgMat);
    pageR.position.set(s * .16, s * .08, 0);
    pageR.rotation.y = -Math.PI * 0.06;
    g.add(pageR);
    // Engraved text lines on left page
    for (let i = 0; i < 4; i++) {
      const tl = new T.Mesh(
        new T.BoxGeometry(s * (.10 + Math.random() * .08), s * .01, s * .002), M_MID());
      tl.position.set(-s * .16, s * .18 - i * s * .065 + s * .08, s * .012);
      g.add(tl);
    }
    // Engraved text lines on right page
    for (let i = 0; i < 4; i++) {
      const tr = new T.Mesh(
        new T.BoxGeometry(s * (.10 + Math.random() * .08), s * .01, s * .002), M_MID());
      tr.position.set(s * .16, s * .18 - i * s * .065 + s * .08, s * .012);
      g.add(tr);
    }
    // Dyson sphere above the book (raised for pedestal clearance)
    const dY = s * .55;
    // Solid core sphere
    const dCore = new T.Mesh(
      new T.SphereGeometry(s * .18, 16, 12),
      new T.MeshStandardMaterial({ color: _pal.m, metalness: .3, roughness: .5 }));
    dCore.position.y = dY;
    g.add(dCore);
    // Accent inner core with subtle emissive
    const dInner = new T.Mesh(
      new T.SphereGeometry(s * .09, 8, 8),
      new T.MeshStandardMaterial({
        color: _pal.l, metalness: .25, roughness: .45,
        emissive: new T.Color(_pal.a), emissiveIntensity: .25
      }));
    dInner.position.y = dY;
    g.add(dInner);
    break;
  }

  // ── gauge ───────────────────────────────────────────────────────────
  // Scorer -- dial gauge
  case 'gauge': {
    const ring = new T.Mesh(new T.TorusGeometry(s * .32, s * .06, 8, 20), M_DARK());
    ring.rotation.x = Math.PI / 2;
    g.add(ring);
    const face = new T.Mesh(new T.CylinderGeometry(s * .28, s * .28, s * .03, 16), M_MID());
    g.add(face);
    const needle = new T.Mesh(new T.BoxGeometry(s * .03, s * .04, s * .28), M_ACCENT());
    needle.position.z = s * .08;
    needle.rotation.z = Math.PI / 5;
    g.add(needle);
    const hub2 = new T.Mesh(new T.SphereGeometry(s * .06, 8, 8), M_LIGHT());
    g.add(hub2);
    break;
  }

  // ── hub ─────────────────────────────────────────────────────────────
  // Router -- network hub
  case 'hub': {
    const center = new T.Mesh(new T.DodecahedronGeometry(s * .28), M_MID());
    center.userData.animate = 'hub_core';
    g.add(center);
    for (let i = 0; i < 6; i++) {
      const a = i * Math.PI / 3;
      const arm = new T.Mesh(new T.CylinderGeometry(s * .025, s * .025, s * .3, 8), M_ACCENT());
      arm.rotation.z = Math.PI / 2;
      arm.position.set(Math.cos(a) * s * .25, 0, Math.sin(a) * s * .25);
      arm.rotation.y = a;
      g.add(arm);
      const tip2 = new T.Mesh(new T.SphereGeometry(s * .05, 8, 8), M_LIGHT());
      tip2.position.set(Math.cos(a) * s * .42, 0, Math.sin(a) * s * .42);
      g.add(tip2);
    }
    break;
  }

  // ── tree ────────────────────────────────────────────────────────────
  // Taxonomy -- branching tree
  case 'tree': {
    const trunk = new T.Mesh(new T.CylinderGeometry(s * .05, s * .08, s * .4, 8), M_DARK());
    g.add(trunk);
    const crown = new T.Mesh(new T.IcosahedronGeometry(s * .28, 0), M_MID());
    crown.position.y = s * .35;
    g.add(crown);
    for (let i = -1; i <= 1; i += 2) {
      const branch = new T.Mesh(new T.CylinderGeometry(s * .02, s * .03, s * .25, 8), M_ACCENT());
      branch.position.set(i * s * .15, s * .15, 0);
      branch.rotation.z = -i * .5;
      g.add(branch);
      const leaf = new T.Mesh(new T.SphereGeometry(s * .1, 8, 8), M_MID());
      leaf.position.set(i * s * .3, s * .28, 0);
      g.add(leaf);
    }
    break;
  }

  // ── sphere ──────────────────────────────────────────────────────────
  // Embedder -- sphere with double orbital rings
  case 'sphere': {
    const sp = new T.Mesh(new T.SphereGeometry(s * .32, 16, 12), M_MID());
    g.add(sp);
    const r1b = new T.Mesh(new T.TorusGeometry(s * .42, s * .015, 8, 24), M_ACCENT());
    r1b.rotation.x = Math.PI / 3;
    g.add(r1b);
    const r2b = new T.Mesh(new T.TorusGeometry(s * .38, s * .012, 8, 24), M_DARK());
    r2b.rotation.y = Math.PI / 2.5;
    r2b.rotation.z = Math.PI / 4;
    g.add(r2b);
    break;
  }

  // ── prism ───────────────────────────────────────────────────────────
  // Crystallizer -- rough form becoming a polished prism
  case 'prism': {
    const rough = new T.Mesh(new T.DodecahedronGeometry(s * .22, 0), M_DARK());
    rough.position.set(-s * .15, -s * .08, 0);
    g.add(rough);
    const prismG = new T.CylinderGeometry(s * .18, s * .22, s * .5, 8);
    const prism = new T.Mesh(prismG, M_LIGHT());
    prism.position.set(s * .08, s * .05, 0);
    prism.userData.animate = 'prism_polished';
    g.add(prism);
    for (let i = 0; i < 3; i++) {
      const spark = new T.Mesh(new T.OctahedronGeometry(s * .04), M_ACCENT());
      spark.position.set(
        s * .2 + Math.random() * s * .1,
        s * .25 + i * s * .08,
        Math.random() * s * .1 - .05);
      g.add(spark);
    }
    break;
  }

  // ── stairs ──────────────────────────────────────────────────────────
  // Promoter -- ascending staircase with arrow
  case 'stairs': {
    for (let i = 0; i < 5; i++) {
      const step = new T.Mesh(
        new T.BoxGeometry(s * (.55 - i * .04), s * .08, s * .3), i < 3 ? M_DARK() : M_MID());
      step.position.set(i * s * .12 - s * .24, i * s * .1 - s * .15, 0);
      g.add(step);
    }
    const arrow = new T.Mesh(new T.ConeGeometry(s * .1, s * .15, 3), M_LIGHT());
    arrow.position.set(s * .3, s * .35, 0);
    g.add(arrow);
    break;
  }

  // ── nexus ───────────────────────────────────────────────────────────
  // Cross-Layer -- layered connected nodes
  case 'nexus': {
    for (let ly = 0; ly < 3; ly++) {
      const plate = new T.Mesh(
        new T.BoxGeometry(s * .6, s * .03, s * .35), ly === 1 ? M_MID() : M_DARK());
      plate.position.y = ly * s * .2 - s * .15;
      g.add(plate);
      for (let nx = 0; nx < 2; nx++) {
        const node = new T.Mesh(new T.SphereGeometry(s * .05, 8, 8), M_LIGHT());
        node.position.set((nx - .5) * s * .3, ly * s * .2 - s * .1, 0);
        g.add(node);
      }
    }
    for (let i = 0; i < 3; i++) {
      const conn = new T.Mesh(new T.CylinderGeometry(s * .012, s * .012, s * .45, 8), M_ACCENT());
      conn.position.set((i - 1) * s * .2, s * .08, 0);
      g.add(conn);
    }
    break;
  }

  // ── graph ───────────────────────────────────────────────────────────
  // Link Predictor -- interconnected graph
  case 'graph': {
    const positions = [
      [0, s * .15, 0],
      [-s * .2, -s * .1, -s * .1],
      [s * .2, -s * .1, s * .1],
      [s * .15, s * .1, -s * .15],
      [-s * .1, -.05, s * .15]
    ];
    positions.forEach(([px, py, pz], i) => {
      const n = new T.Mesh(
        new T.SphereGeometry(i === 0 ? s * .1 : s * .07, 8, 8),
        i === 0 ? M_LIGHT() : M_MID());
      n.position.set(px, py, pz);
      g.add(n);
    });
    [[0, 1], [0, 2], [0, 3], [1, 4], [2, 3], [3, 4]].forEach(([a, b]) => {
      const pa = positions[a], pb = positions[b];
      const dir = new T.Vector3(pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]);
      const len = dir.length();
      dir.normalize();
      const cyl = new T.Mesh(new T.CylinderGeometry(s * .01, s * .01, len, 8), M_ACCENT());
      cyl.position.set((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2);
      cyl.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), dir);
      g.add(cyl);
    });
    break;
  }

  // ── dial ────────────────────────────────────────────────────────────
  // Adaptive -- control dial with indicator
  case 'dial': {
    const base3 = new T.Mesh(new T.CylinderGeometry(s * .32, s * .35, s * .18, 16), M_DARK());
    g.add(base3);
    const knob = new T.Mesh(new T.CylinderGeometry(s * .2, s * .2, s * .1, 12), M_MID());
    knob.position.y = s * .14;
    g.add(knob);
    const indicator = new T.Mesh(new T.BoxGeometry(s * .04, s * .08, s * .22), M_LIGHT());
    indicator.position.set(0, s * .22, s * .05);
    indicator.userData.animate = 'dial_indicator';
    g.add(indicator);
    for (let i = 0; i < 8; i++) {
      const a = i * Math.PI / 4;
      const tick = new T.Mesh(new T.BoxGeometry(s * .02, s * .04, s * .06), M_ACCENT());
      tick.position.set(Math.cos(a) * s * .28, s * .14, Math.sin(a) * s * .28);
      tick.rotation.y = -a;
      g.add(tick);
    }
    break;
  }

  // ── vault ───────────────────────────────────────────────────────────
  // Trust Engine -- secure vault with lock
  case 'vault': {
    const body = new T.Mesh(new T.BoxGeometry(s * .6, s * .55, s * .5), M_DARK());
    g.add(body);
    const door2 = new T.Mesh(new T.BoxGeometry(s * .45, s * .4, s * .02), M_MID());
    door2.position.z = s * .26;
    g.add(door2);
    const lockRing = new T.Mesh(new T.TorusGeometry(s * .1, s * .02, 8, 16), M_LIGHT());
    lockRing.position.set(0, 0, s * .28);
    g.add(lockRing);
    const lockCenter = new T.Mesh(new T.CylinderGeometry(s * .04, s * .04, s * .03, 8), M_ACCENT());
    lockCenter.position.set(0, 0, s * .29);
    lockCenter.rotation.x = Math.PI / 2;
    g.add(lockCenter);
    const handle = new T.Mesh(new T.CylinderGeometry(s * .02, s * .02, s * .2, 8), M_ACCENT());
    handle.position.set(s * .18, 0, s * .28);
    handle.rotation.z = Math.PI / 2;
    g.add(handle);
    for (const [bx, by] of [[-0.18, 0.16], [0.18, 0.16], [-0.18, -0.16], [0.18, -0.16]]) {
      const bolt = new T.Mesh(new T.CylinderGeometry(s * .02, s * .02, s * .04, 8), M_LIGHT());
      bolt.position.set(bx * s, by * s, s * .27);
      bolt.rotation.x = Math.PI / 2;
      g.add(bolt);
    }
    break;
  }

  // ── screens ─────────────────────────────────────────────────────────
  // LLM -- three monitors
  case 'screens': {
    for (let i = -1; i <= 1; i++) {
      const fr = new T.Mesh(new T.BoxGeometry(s * .38, s * .3, s * .05), M_DARK());
      fr.position.set(i * s * .28, s * .08, 0);
      fr.rotation.y = i * -.2;
      g.add(fr);
      const face2 = new T.Mesh(new T.PlaneGeometry(s * .3, s * .22), M_SCREEN());
      face2.position.set(i * s * .28, s * .08, s * .028);
      face2.rotation.y = i * -.2;
      g.add(face2);
    }
    const stand = new T.Mesh(new T.CylinderGeometry(s * .04, s * .06, s * .22, 8), M_ACCENT());
    stand.position.y = -s * .15;
    g.add(stand);
    const base4 = new T.Mesh(new T.BoxGeometry(s * .5, s * .03, s * .2), M_MID());
    base4.position.y = -s * .26;
    g.add(base4);
    break;
  }

  // ── rack ────────────────────────────────────────────────────────────
  // MCP Server -- tall server rack with details
  case 'rack': {
    const frame = new T.Mesh(new T.BoxGeometry(s * .5, s * .65, s * .4), M_DARK());
    g.add(frame);
    for (let i = 0; i < 5; i++) {
      const unit = new T.Mesh(
        new T.BoxGeometry(s * .44, s * .08, s * .35), i % 2 === 0 ? M_MID() : M_DARK());
      unit.position.y = i * s * .11 - s * .22;
      unit.position.z = s * .02;
      g.add(unit);
      const led = new T.Mesh(
        new T.SphereGeometry(s * .015, 12, 12),
        new T.MeshBasicMaterial({ color: 0x34d399 }));
      led.position.set(s * .18, i * s * .11 - s * .22, s * .2);
      g.add(led);
    }
    break;
  }

  // ── conveyor ────────────────────────────────────────────────────────
  // CI/CD -- conveyor belt with gears
  case 'conveyor': {
    const belt = new T.Mesh(new T.BoxGeometry(s * .8, s * .06, s * .35), M_DARK());
    belt.position.y = -s * .1;
    g.add(belt);
    for (const rx of [-s * .32, 0, s * .32]) {
      const roller = new T.Mesh(new T.CylinderGeometry(s * .06, s * .06, s * .38, 8), M_MID());
      roller.rotation.x = Math.PI / 2;
      roller.position.set(rx, -s * .06, 0);
      g.add(roller);
    }
    for (let i = 0; i < 3; i++) {
      const item = new T.Mesh(new T.BoxGeometry(s * .12, s * .1, s * .15), M_LIGHT());
      item.position.set(-s * .25 + i * s * .25, s * .02, 0);
      item.userData.animate = 'conv_item';
      item.userData.convIdx = i;
      g.add(item);
    }
    const arr = new T.Mesh(new T.ConeGeometry(s * .08, s * .12, 3), M_ACCENT());
    arr.position.set(s * .45, s * .05, 0);
    arr.rotation.z = -Math.PI / 2;
    g.add(arr);
    break;
  }

  // ── monitor ─────────────────────────────────────────────────────────
  // IDE -- large detailed monitor
  case 'monitor': {
    const scrF = new T.Mesh(new T.BoxGeometry(s * .7, s * .48, s * .05), M_DARK());
    scrF.position.y = s * .1;
    g.add(scrF);
    const scrD = new T.Mesh(new T.PlaneGeometry(s * .58, s * .38), M_SCREEN());
    scrD.position.set(0, s * .1, s * .03);
    g.add(scrD);
    for (let i = 0; i < 4; i++) {
      const line = new T.Mesh(
        new T.BoxGeometry(s * (.3 + Math.random() * .15), s * .015, s * .001),
        new T.MeshBasicMaterial({ color: 0x2a3a5a }));
      line.position.set(-s * .05, s * .18 - i * s * .06, s * .032);
      g.add(line);
    }
    const stand3 = new T.Mesh(new T.BoxGeometry(s * .08, s * .2, s * .1), M_ACCENT());
    stand3.position.y = -s * .14;
    g.add(stand3);
    const base5 = new T.Mesh(new T.BoxGeometry(s * .35, s * .03, s * .18), M_MID());
    base5.position.y = -s * .25;
    g.add(base5);
    break;
  }

  // ── default fallback ───────────────────────────────────────────────
  default: {
    g.add(new T.Mesh(new T.BoxGeometry(s * .5, s * .5, s * .5), M_DARK()));
  }

  } // end switch

  return g;
}
