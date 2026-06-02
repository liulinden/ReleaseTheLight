import pygame
import pathlib
import threading
from queue import Queue

ASSETS = pathlib.Path("assets")

FPS = 15 # low FPS

class TitleSpinner(pygame.sprite.Sprite):
    def __init__(self, frames: list[pygame.Surface], fps):
        super().__init__()

        self.frames = frames
        self.frame_index = 0

        self.image = self.frames[self.frame_index]
        self.rect = self.image.get_rect()

        self.previous_time = pygame.time.get_ticks()
        self.frame_duration = 1000 // fps
    
    def update(self):
        current_time = pygame.time.get_ticks()
        if current_time - self.previous_time >= self.frame_duration:
            self.previous_time = current_time
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            self.image = self.frames[self.frame_index]

class LoadingBar(pygame.sprite.Sprite):
    def __init__(self, size: tuple[int, int]):
        super().__init__()
        
        self.image = pygame.Surface(size, pygame.SRCALPHA)
        self.rect = self.image.get_rect()
        self.set_progress(0)
    
    def set_progress(self, progress: float):
        self.progress = progress

        outer_rect = self.image.get_rect()
        pygame.draw.rect(self.image, (0,0,0,150), outer_rect, border_radius=10)
        pygame.draw.rect(self.image, "white", outer_rect, width=3, border_radius=10)

        inner_rect = outer_rect.inflate(-15, -15)
        inner_rect.width *= self.progress
        pygame.draw.rect(self.image, "white", inner_rect, border_radius=5)

    def get_progress(self):
        return self.progress

class LoadingScreen:
    def __init__(self, surface: pygame.Surface, *, _queue=None, start_progress=0, end_progress=1):

        self.surface = surface

        self.start_progress = start_progress
        self.end_progress = end_progress

        if _queue is None:
            self.queue = Queue()
        else:
            self.queue = _queue

    def _title_frames(self):
        frames = []
        size = int(self.surface.get_height() * (2/3))
        for i in range(8):
            frame = pygame.image.load(ASSETS / "TitleSpinner" / f"frame_{i}.webp").convert_alpha()
            frame = pygame.transform.scale(frame, (size, size))
            frames.append(frame)
        return frames

    def _gradient(self):
        size = self.surface.get_width()
        gradient = pygame.image.load(ASSETS / "VignetteGradientTitle.webp").convert_alpha()
        gradient = pygame.transform.scale(gradient, (size, size))
        return gradient

    def put(self, progress):
        progress = self.start_progress + (self.end_progress - self.start_progress) * progress
        self.queue.put(progress)
    
    def run_on_thread(self):
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread
    
    def subsection(self, start_at, end_at) -> "LoadingScreen":
        return LoadingScreen(self.surface, _queue=self.queue, start_progress=start_at, end_progress=end_at)

    def run(self) -> bool:
        going = True

        clock = pygame.time.Clock()

        font = pygame.font.SysFont("Arial", self.surface.get_height() // 20)

        loading_bar = LoadingBar((self.surface.get_width() // 3, self.surface.get_height() // 50))
        title_spinner = TitleSpinner(self._title_frames(), 12)

        gradient = self._gradient()

        title_spinner.rect.center = (self.surface.get_width() // 2, self.surface.get_height() // 2)
        loading_bar.rect.midtop = (self.surface.get_width() // 2, self.surface.get_height() // 100 * 72)

        sprites = pygame.sprite.Group(title_spinner, loading_bar)

        progress = self.start_progress
        loading_bar.set_progress(progress)

        while going and progress < self.end_progress:

            self.surface.fill("black")
            self.surface.blit(gradient, gradient.get_rect(center=title_spinner.rect.center))

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
                loading_bar.set_progress(progress)

            pygame.display.flip()
            clock.tick(FPS)
        
        return going
