Shader and Sprite Repositories - Ranked for the Four Tools



In this document the ~200 repositories from the provided list are organised by the four tools WIZARD, SWIFT, SHADED, and PIPELINE/QA. The ranking is based on how well each repository aligns with our Beuteschema - namely how it can be re-purposed, combined, or extended to support our goals rather than simply being a finished product.



Note: For brevity the repositories are grouped into high-, medium- and low-priority tiers. Only the most promising entries receive detailed comments. Other entries are listed to show completeness of the sorting; they may still hold value but are less aligned with our immediate aims. Where relevant, citations from the GitHub projects are provided.



WIZARD - Asset & Knowledge



High-priority



1. LibreSprite - a fully fledged pixel-art editor; use its project structure to build an asset-management UI that



can



2.



3.



4.



5.



integrates with WIZARD. Adapting its sprite format would let us ingest user-created assets directly.



Pixelorama - another open-source pixel editor; the source can be mined to understand how to store and



export layered animation frames in a simple JSON format. Combining this with WIZARD would allow on-device asset editing.



FE-Repo - an extensive collection of Fire Emblem sprites and animations. These ready-made assets seed WIZARD's starter kits for 2D tactical games; the metadata can be scraped and normalised into WIZARD's taxonomy.



Blender-spritesheets - scripts for exporting Blender animations into sprite sheets; this can be turned into a WIZARD plug-in to generate 2D representations from high-poly 3D models. It bridges our 3D asset library into SWIFT.



SpriterDotNet - C# library for parsing Spriter files; the code shows how to read bone-based animation data. WIZARD could use this logic to interpret third-party animation files and convert them into a neutral intermediate representation.



Medium-priority



Sprite Factory, Sprite.js, Tile-Studio, SpookyGhost, Ganim8-lib, Character-animation-creator-skill - these tools provide various data formats (JSON, XML) for sprites, animations and tiles. They offer insights into how to structure 2D asset metadata and could inform WIZARD's schema.



NinjaRipper, ProjectKaya, Renpy-template, Image-cockpit - asset extraction or template repositories useful for building import/export workflows.



Low-priority



Gorest-2d-animation-spritesheet-generator, Sprite-timeline, Motio, PerfectPixel-studio, ShadowEngine, Morphin, RetroNick2020/raster-master, KritaSpritesheetManager - these are single-purpose tools whose code is worth scanning for ideas but unlikely to be core to WIZARD.



:the



SWIFT - Procedural Sprite & Animation



High-priority



1.



2.



3.



4.



5.



UnitySpritesAndBones - skeleton-based 2D animation system for Unity. It demonstrates how to drive meshes via bones and could inform SWIFT's rigging pipeline; the approach to storing bone transforms is valuable for our sprite-sheet generator.



SpriteKit-Spring - provides spring-based animations in SpriteKit; the code shows how to add damping and initial velocity parameters to animation actions github.com. This can be translated to SWIFT to add physics-based secondary motion to procedurally generated sprites.



UIKitAnimationPro - creates animation sequences in UIKit similar to cocos2d's CCAction github.com sequence API can inspire a declarative animation DSL for SWIFT that composes multiple actions (move, rotate, scale, fade) with easing.



SpriteKit-Water-Node - 2D water simulation node that chains a fragment shader with a physics solver github.com. By studying its approach, SWIFT can simulate surfaces like cloth, jello or fabric to enrich sprites.



SpookyGhost - generates spooky effects for sprite animations; the technique of procedurally blending frames to add ghost trails can be re-used in SWIFT's effect layer.



Medium-priority



Blender-spritesheets, Motio, rn-sprite-sheet, Sprite-gen, Sprite.js, Canvas-Sprite-Animations, Smoothie, Ganim8-lib - all provide examples of generating or playing back sprite sheets in different languages. Their algorithms for packing frames and computing animation timings can help SWIFT's sprite-sheet compiler.



UnityStylizedWater, UIEffect - though shader-oriented, these Unity resources illustrate how to pack



dynamic effects into materials that apply to 2D sprites.



Low-priority



Image-cockpit-for-codex-workflows, Sprite-wxapp, Godot-animated-sprite-2-player, Sprite-timeline, Point maps - specific to certain frameworks; less relevant unless we port to those frameworks.



SHADED - Shader & World Simulation



High-priority



1.



2.



3.



4.



5.



The Book of Shaders - an extensive tutorial covering shader basics, algorithmic drawing, noise, fractals and image processing github.com. This is an excellent conceptual guide for building SHADED's ontology



of visual effects.



LYGIA - a multi-language shader library for GLSL, HLSL, Metal, WGSL and CUDA github.com. It offers modular shader functions (noise, blur, normal maps) that can be recomposed; perfect for building



SHADED's standard library and enabling code generation across languages.



ShaderGlass - overlays GPU shaders on top of the Windows desktop, with a library of image-processing effects github.com. The concept of applying shaders to arbitrary buffers can inspire SHADED's Preview Glass for live visualisation of world states.



SHADERed - cross-platform shader IDE with debugger github.com. It demonstrates how to build an interactive environment with uniform inspectors and texture inputs; this is useful for our planned Shaded Lab



Shader-slang - shading language designed to make writing and maintaining large shader codebases easier github.com. Its modular compilation model could inform our own intermediate representation (Effect IR) to target multiple backends.



6. GIsIViewer - console-based GLSL sandbox github.com - simple yet effective; we can repurpose its



7.



runtime to execute our generated shaders in headless or browser contexts.



AIShader - proof-of-concept ChatGPT-powered shader generator github.com; it hints at the feasibility of using generative models to create shader code from high-level descriptions - a feature we plan to embed



into Shaded Effect Forge.



Medium-priority



Shader-school, ShaderEditor, ShaderMinifier, ShaderPlayground, ReShade HDR shaders, Lamina,



Common-shaders, Libretro/common-shaders, ShaderParticleEngine, Shader ToHuman - these repos provide either learning material or collections of shaders for postprocessing, particles and stylised effects.



They are valuable references when composing new layers and studying code patterns.



Gl-React, Curtains.js, p5jsShaderExamples, Shader-park-core, Shadertoy examples - these show how shaders can be integrated into JS/TS frameworks. They demonstrate runtime hot-reloading and parameter binding, which can guide our browser-based tools.



KhronosGroup/glslang, Google/shaderc, Mojoshader - compilers and transpilers; necessary to support



multiple back-ends but lower priority than the design of our effect abstractions.



Fast-gaussian-rasterization, DiffusionAsShader, SDF libraries - research-grade shading techniques; they



can inspire advanced features like volumetric splatting or diffusion-driven effects.



Low-priority



Hundreds of small effect demos (Water Shader, Toon Water Shader, Rainbows, Ink Painting etc.) - interesting stylistically but not essential to our architecture. We can revisit them once SHADED's core is in



place.



PIPELINE / QA - Compute, Translation & Debugging



High-priori



1. GPU-io - GPU-accelerated computing library for physics simulation, particle systems and image processing github.com. This demonstrates how to build a unified API over WebGL to run arbitrary compute kernels. It can inspire the design of our Field Engine to simulate snow, wetness, heat or footsteps as dynamic texture







Compute-Shader-101 - sample code and documentation on writing compute shader applications github.com. It emphasises the portability and toolchain issues of compute shaders and suggests usi



WebGPU. This knowledge helps define our cross-platform compute runtim



3. GraphicsFuzz - tests GPU drivers for shader correctness and robustness. Its corpus of fuzzed shade











can be used by our QA agent to validate that our generated shaders work across device



Shader-Reload - live reload system for shaders. Integrating such a hot-reload mechanism into o



pipeline ensures a smooth development workflow and underpins SHADED's interactive edito



SPIRV-VM - a virtual machine for SPIR-V; useful for executing and debugging compiled shaders in isolatio



Medium-priori



Shader-Park-core, Shader-playground - show how to host code editors with live preview and compute support. They can be used as reference implementations for our internal tool



HLSL-Spherical-Harmonics, Mochies-Unity-shaders - demonstration of complex lighting models; th



offer test cases for our pipeline's translation uni



⚫ Shader-c, GLSLang - as above, important back-end tools but not immediate to our desig



Low-priori



Many small compute demos (crowd rendering, volumetric fog, occlusion culling) are interesting but outside the first pass. We can integrate them later as specific QA test



Summa



The list contains a wide variety of repositories. By categorising them into WIZARD, SWIFT, SHADED, and PIPELINE/QA we can focus on those that provide actionable structures, data formats, or algorithms rather than finished products. The high-priority items offer the most immediate value: they either expose intermediate representations we can adopt, procedural algorithms we can adapt, or editor paradigms we can emulate. Medium-priority items serve as reference or inspiration, while low-priority items may be revisited once the core pipeline is establishe



Citation



Tutorial coverage of shader basics and topics such as algorithmic drawing and image processi



github.c



Modular multi-language shader library description github.c



Shader IDE features summary github.c



Fragment shader workflow details for SpriteKit github.c



UIKit animation sequencing capabilities github.c



Water simulation node description github.c



Compute shader overview and portable run-time discussion github.co



GPU-accelerated computing library introduction github.comm.omomomomomomngs:d.rys.tyn.t.eys.tyn.r.urs.5.4.rse.ng2.s.ty



