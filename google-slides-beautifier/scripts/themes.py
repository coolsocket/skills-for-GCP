class Themes:
    GLASS = {
        "name": "glass",
        "description": "High-fidelity, futuristic glassmorphism with neon accents.",
        "prompt_template": {
            "default": """
You are an expert UI UX presentation designer. Generate a high-fidelity 16:9 presentation slide image.

STYLE - GRADIENT GLASSMORPHISM:
- **Visuals**: Mix of Apple Keynote minimalism and modern SaaS glassmorphism. High-end, immersive, clean.
- **Lighting**: Cinematic volumetric lighting, soft ray-tracing reflections.
- **Colors**: Deep void black or ceramic white base. Flowing aurora gradients (neon purple, electric blue, soft coral) for background and highlights.
- **Layout**: Bento grid system. Modular rounded rectangles.
- **Material**: Frosted glass with refined white edges and soft shadows. ample whitespace.
- **3D Elements**: Abstract high-end 3D objects (polished metal, iridescent acrylic, glass spheres) as visual anchors.
- **Typography**: Clean sans-serif, high contrast.
- **Quality**: Unreal Engine 5 render, 8k resolution, ultra-detailed textures.

PAGE CONTEXT:
{content}

INSTRUCTIONS:
- Design a beautiful slide based on the content above.
- Use the Bento grid layout for content.
- OUTPUT: A single 16:9 high-resolution image.
""",
            "cover": """
You are an expert UI UX presentation designer. Generate a high-fidelity 16:9 COVER slide.

STYLE - GRADIENT GLASSMORPHISM:
- **Visuals**: Apple Keynote minimalism mixed with high-end glassmorphism.
- **Centerpiece**: A huge, complex 3D glass object (abstract shape, capsule, or sphere) in the center.
- **Typography**: HUGE, BOLD text overlaying the object or floating in front of it.
- **Background**: Extending aurora waves. deep void black or ceramic white.

CONTENT:
{content}

INSTRUCTIONS:
- Place the Title text prominently.
- Ensure the 3D object is stunning and central.
- OUTPUT: A single 16:9 high-resolution image.
""",
            "data": """
You are an expert UI UX presentation designer. Generate a high-fidelity 16:9 DATA slide.

STYLE - GRADIENT GLASSMORPHISM:
- **Layout**: Split screen design.
- **Left Side**: Clean typography area for text.
- **Right Side**: HUGE glowing 3D data visualization (floating donut chart, capsule progress bars, neon numbers).
- **Style**: Looks like a neon light toy or high-end HUD.

CONTENT:
{content}

INSTRUCTIONS:
- Visualize the data points creatively.
- OUTPUT: A single 16:9 high-resolution image.
"""
        }
    }

    VECTOR = {
        "name": "vector",
        "description": "Warm, flat vector illustrations with vintage aesthetic.",
        "prompt_template": {
            "default": """
You are an expert illustrator. Generate a 16:9 presentation slide image in Flat Vector Illustration style.

STYLE - RETRO VECTOR:
- **Illustration**: Flat vector style. Clear, uniform black monoline outlines (Stroke).
- **Colors**: Retro pastels (Coral Red, Mint Green, Mustard Yellow). Cream/Off-white paper texture background.
- **No Gradients**: Strictly flat colors or simple patterns.
- **Composition**: Panoramic or 2.5D isometric.
- **Shapes**: Geometric simplification ("Toy model" aesthetic). Trees as lollipops, buildings as blocks.
- **Decor**: Geometric elements (dots, stars, sun rays) to fill void space.

PAGE CONTEXT:
{content}

INSTRUCTIONS:
- Create a horizontal illustration band at the top or side.
- Use colored rectangles to separate content points.
- OUTPUT: A single 16:9 high-resolution image.
""",
            "cover": """
You are an expert illustrator. Generate a 16:9 COVER slide in Flat Vector Illustration style.

STYLE - RETRO VECTOR:
- **Composition**: Horizontal panoramic illustration occupying the top 1/3.
- **Subject**: Geometric city/landscape with "Toy model" aesthetic.
- **Typography**: HUGE, BOLD Retro Serif font for the Title.
- **Background**: Beige/Cream paper texture.

CONTENT:
{content}

INSTRUCTIONS:
- Focus on the vintage typography and the top illustration band.
- OUTPUT: A single 16:9 high-resolution image.
""",
            "data": """
You are an expert illustrator. Generate a 16:9 DATA slide in Flat Vector Illustration style.

STYLE - RETRO VECTOR:
- **Visuals**: Geometric vector charts (pie charts, bar charts) with thick black outlines.
- **Colors**: Retro pastel palette.
- **Decor**: Small stars, dots, and lines affecting balance.

CONTENT:
{content}

INSTRUCTIONS:
- Make the charts look like flat vector illustrations.
- OUTPUT: A single 16:9 high-resolution image.
"""
        }
    }

    @classmethod
    def get_theme(cls, name):
        if name.lower() == "glass": return cls.GLASS
        if name.lower() == "vector": return cls.VECTOR
        if name.lower() == "retro": return cls.VECTOR # Alias
        return None
