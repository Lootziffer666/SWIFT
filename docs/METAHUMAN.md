# MetaHuman → SWIFT → SHADED

MetaHumans sind vollständig geriggte, animierbare Menschen aus Epics MetaHuman
Creator. Für das agentische Studio (assetpilot.md) sind sie die **Quelle für
realistische menschliche Figuren**: SWIFT rendert den UE-FBX-Export zu
Sprite-Sheets + Manifest, SHADED lädt sie als optische Actors. MetaHuman wird
damit zur FBX-Quelle in der bestehenden Pipeline — keine Engine-Abhängigkeit
zur Laufzeit, Invariante 2 (Material-Wahrheit) bleibt unberührt.

```
MetaHuman Creator → UE5 (Quixel Bridge) → FBX-Export → SWIFT render → SHADED addActor
```

## Export aus Unreal Engine

1. MetaHuman im [MetaHuman Creator](https://metahuman.unrealengine.com/)
   gestalten und über Quixel Bridge in ein UE5-Projekt laden.
2. Im Content Browser das Skeletal Mesh des MetaHuman wählen →
   **Asset Actions → Export** → FBX.
   - **LOD wählen:** LOD 2–4 genügt völlig — SWIFT pixelisiert ohnehin
     (Standard-Framegröße 64×64). LOD 0 (Film-Qualität) macht den Export nur
     langsam und groß.
   - **Animation:** entweder direkt eine Animation Sequence mit exportieren
     oder eine separate Anim-FBX (Retarget auf das MetaHuman-Skelett in UE)
     als `--anim` übergeben.
3. Benennung: `metahuman_<name>.fbx` bzw. Präfix `MH_` — SWIFTs Anim-Library
   erkennt die Quelle dann automatisch als `MetaHuman (Epic)`.

## Rendern mit SWIFT

```bash
python main.py render \
  --model metahuman_hero.fbx \
  --anim mh_walk.fbx \
  --format sprite_sheet \
  --width 96 --height 96 \
  --depth-pass --emissive-pass \
  --world-states dust,aging \
  --output out/hero
# -> out/hero.png, out/hero_manifest.json, out/hero_depth.png,
#    out/hero_emissive.png, out/hero_dust.png, out/hero_aging.png
```

Hinweise:

- **Materialien:** MetaHuman-Materialien (Haut-Shader, Groom-Haare) überleben
  den FBX-Export nicht vollständig. Für Pixel-Art ist das unerheblich — die
  Silhouette und Grundfarben tragen den Look. Wer mehr Farbtreue will,
  exportiert mit eingebetteten Texturen (FBX-Option „Embed Media").
- **Maßstab:** MetaHumans sind realmaßstäblich (~180 cm). Die Kamera-Anpassung
  von SWIFT rahmt das Modell automatisch; bei Gruppenszenen in SHADED die
  relative Größe über `addActor({scale})` steuern.
- **Frame-Größe:** 96×96 statt 64×64 gibt menschlichen Proportionen etwas mehr
  Lesbarkeit, bleibt aber klar Pixel-Art.

## In SHADED laden

```js
const manifest = await fetch('hero_manifest.json').then(r => r.json());
window.SHADED.addActor({
  image: 'hero.png',
  manifest,
  depthImage: 'hero_depth.png',
  emissiveImage: 'hero_emissive.png',
  worldStateImages: { dust: 'hero_dust.png', aging: 'hero_aging.png' },
  x: 0.5, y: 0.62, anim: 'walk', depthLayer: 'mid',
});
```

## Lizenz

MetaHumans dürfen laut Epic-Lizenz nur in **Unreal-Engine-Produkten**
verwendet werden. Der SWIFT/SHADED-Weg zielt auf UE/UEFN-Prototypen im Sinne
von assetpilot.md („Unreal in a Box"); für Nicht-UE-Ziele stattdessen SWIFTs
prozeduralen Skelett-Generator oder CC0-Quellen (UAL/Quaternius) nutzen.
WIZARDs Production-Brief empfiehlt den passenden Weg automatisch
(`characterPipeline`).
