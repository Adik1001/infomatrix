from PIL import Image, ImageDraw
import random

def create_bg():
    width = 1920
    height = 1080
    img = Image.new('RGB', (width, height), color='#1a1a2e')
    draw = ImageDraw.Draw(img)
    
    # Draw some random stars/shapes
    for _ in range(100):
        x = random.randint(0, width)
        y = random.randint(0, height)
        r = random.randint(1, 3)
        draw.ellipse((x-r, y-r, x+r, y+r), fill='#ffffff', outline=None)
        
    img.save("background.png")

if __name__ == "__main__":
    create_bg()
