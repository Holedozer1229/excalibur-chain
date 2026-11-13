from PIL import Image
import os

logo_path = os.path.join(os.path.dirname(__file__), "logo.jpeg")
output_path = os.path.join(os.path.dirname(__file__), "gui", "public", "logo.png")

img = Image.open(logo_path)
img = img.resize((512, 512), Image.LANCZOS)
img.save(output_path, "PNG")
print(f"Created {output_path}")
