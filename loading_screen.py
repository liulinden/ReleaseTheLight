import pygame
import pathlib
import threading
from queue import Queue

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

        self.last_time = pygame.time.get_ticks()

    def set_position(self, position):
        self.rect.center = position

    def get_image_for_rotation(self, rotation, exact, _memo={}):

        if not exact:
            rotation = int(rotation)
        rotation = rotation % 360

        if rotation not in _memo:
            image = pygame.transform.rotate(self.original_image, -rotation)
            image.blit(self.center_image, self.center_image.get_rect(center=image.get_rect().center))
            if exact:
                return image
            _memo[rotation] = image
        return _memo[rotation]

    def update(self):
        error = self.goal_rotation - self.current_rotation

        current_time = pygame.time.get_ticks()
        time_delta = current_time - self.last_time
        self.last_time = current_time

        rotational_speed = error * 0.0025 * time_delta
        self.current_rotation += rotational_speed

        if abs(error) < 0.1:
            self.goal_rotation += 360 // 6

        self.image = self.get_image_for_rotation(self.current_rotation, exact = rotational_speed < 2)
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

class LoadingScreen:
    def __init__(self, surface: pygame.Surface):

        self.surface = surface

        h = self.surface.get_height()

        self.title_image = pygame.transform.scale(pygame.image.load(ASSETS / "TitleImage.webp"), (h * 0.7, h * 0.7)).convert_alpha()
        self.title_background_image = pygame.transform.scale(pygame.image.load(ASSETS / "LoadingStar.webp"), (h * 0.75, h * 0.75)).convert_alpha()
        self.title_glow = pygame.transform.scale(pygame.image.load(ASSETS / "VignetteGradient.png"), (h * 1.2, h * 1.19)).convert_alpha()

        self.font = pygame.font.SysFont("Arial", self.surface.get_height() // 20)

        self.loading_bar = LoadingBar((self.surface.get_width() // 3, self.surface.get_height() // 20))
        self.title_spinner = TitleSpinner(self.title_background_image, self.title_image)

        self.queue = Queue()

    def get_queue(self):
        return self.queue
    
    def run_threaded(self, end_at = 1):
        thread = threading.Thread(target=self.run, args=(end_at,), daemon=True)
        thread.start()
        return thread

    def run(self, end_at = 1):
        going = True

        clock = pygame.time.Clock()

        sprites = pygame.sprite.Group(self.title_spinner, self.loading_bar)

        self.title_spinner.rect.center =(self.surface.get_width() // 2, self.surface.get_height() // 100 * 35)
        self.loading_bar.rect.center = (self.surface.get_width() // 2, self.surface.get_height() // 100 * 80)

        progress = 0

        while going and progress < end_at:

            self.surface.fill("black")
            self.surface.blit(self.title_glow, self.title_glow.get_rect(center=self.title_spinner.rect.center))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    going = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        going = False
            
            sprites.update()
            sprites.draw(self.surface)

            if not self.queue.empty():
                progress = self.queue.get()
                self.loading_bar.set_progress(progress)
                if progress >= end_at:
                    break

            # text = self.font.render(f"{clock.get_fps():.2f} FPS", True, "white")
            # self.surface.blit(text, text.get_rect(topright=self.surface.get_rect().topright))

            # text = self.font.render(f"Loading... {int(progress * 100)}%", True, "white")
            # self.surface.blit(text, text.get_rect(center=(self.surface.get_width() // 2, self.surface.get_height() // 100 * 90)))

            pygame.display.flip()
            clock.tick(FPS)
        
        # print("Loading screen done with progress", progress)
        return going
