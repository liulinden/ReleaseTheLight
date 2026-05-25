import pygame
import threading
from queue import Queue
import pathlib

ASSETS = pathlib.Path("assets")

FPS = 15 # low FPS

class TitleSpinner(pygame.sprite.Sprite):
    def __init__(self, image: pygame.Surface, center_image: pygame.Surface):
        super().__init__()
        self.image = self.original_image = image
        self.center_image = center_image

        self.rect = self.original_image.get_rect()

        self.current_rotation = -1
        self.goal_rotation = 0

    def set_position(self, position):
        self.rect.center = position

    def update(self):
        error = self.goal_rotation - self.current_rotation
        self.current_rotation += error * 0.1

        if abs(error) < 0.1:
            self.goal_rotation += 360 // 6 + 0.05

        self.image = pygame.transform.rotate(self.original_image, -self.current_rotation)
        self.image.blit(self.center_image, self.center_image.get_rect(center=self.image.get_rect().center))

        self.rect = self.image.get_rect(center=self.rect.center)

class LoadingBar(pygame.sprite.Sprite):
    def __init__(self, size: tuple[int, int]):
        super().__init__()
        
        self.image = pygame.Surface(size)
        self.rect = self.image.get_rect()
        self.set_progress(0)
    
    def set_progress(self, progress: float):
        self.progress = progress

        outer_rect = self.image.get_rect()
        pygame.draw.rect(self.image, "white", outer_rect, width=3, border_radius=10)

        inner_rect = outer_rect.inflate(-15, -15)
        inner_rect.width *= self.progress
        pygame.draw.rect(self.image, "white", inner_rect, border_radius=5)

    def get_progress(self):
        return self.progress

def make_blur_image(image_size: int):
    title_background_image = pygame.transform.scale(pygame.image.load(ASSETS / "TitleBackground.webp"), (image_size, image_size))
    title_background_glow_image = pygame.transform.scale(pygame.image.load(ASSETS / "TitleBackgroundGlow.webp"), (image_size * 2, image_size * 2))

    surf_array = pygame.surfarray.pixels_alpha(title_background_glow_image)
    surf_array //= 2
    del surf_array    # unlock the surface

    title_background_glow_image.blit(title_background_image, title_background_image.get_rect(center=title_background_glow_image.get_rect().center))

    title_background_image_scaled = pygame.transform.scale(title_background_image, title_background_glow_image.get_size())

    surf_array = pygame.surfarray.pixels_alpha(title_background_image_scaled)
    surf_array //= 100
    del surf_array

    title_background_glow_image.blit(title_background_image_scaled, title_background_image_scaled.get_rect(center=title_background_glow_image.get_rect().center), special_flags=pygame.BLEND_RGBA_ADD)
    return title_background_glow_image.convert_alpha()

def make_title_image(image_size: int):
    title_image = pygame.transform.scale(pygame.image.load(ASSETS / "TitleImage.webp"), (image_size, image_size)).convert_alpha()
    return title_image

class LoadingScreen:
    def __init__(self, surface: pygame.Surface):

        self.surface = surface

        image_size = int(self.surface.get_height() * 0.7)

        self.title_image = make_title_image(image_size)
        self.title_background_image = make_blur_image(image_size)

        self.font = pygame.font.SysFont(None, 24)

    def start_thread(self):
        queue = Queue()
        self.process = threading.Thread(target=self.run, args=(queue,), daemon=True)
        self.process.start()
        return queue

    def run(self, queue: Queue):
        going = True

        clock = pygame.time.Clock()

        spinner = TitleSpinner(self.title_background_image, self.title_image)
        loading_bar = LoadingBar((self.surface.get_width() // 3, self.surface.get_height() // 20))

        sprites = pygame.sprite.Group(spinner, loading_bar)

        spinner.rect.center =(self.surface.get_width() // 2, self.surface.get_height() // 100 * 35)
        loading_bar.rect.center = (self.surface.get_width() // 2, self.surface.get_height() // 100 * 80)

        progress = 0

        while going and progress < 1:

            self.surface.fill("black")

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    going = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        going = False
            
            sprites.update()
            sprites.draw(self.surface)

            if not queue.empty():
                progress = queue.get()
                loading_bar.set_progress(progress)

            text = self.font.render(f"{clock.get_fps():.2f} FPS", True, "white")

            self.surface.blit(text, text.get_rect(topright=self.surface.get_rect().topright))

            pygame.display.flip()
            clock.tick(FPS)
