import pathlib
import threading
from queue import Queue

import pygame

ASSETS = pathlib.Path("assets")

FPS = 15 # low FPS

class TitleSpinner(pygame.sprite.Sprite):
    def __init__(self, frames: list[pygame.Surface], fps: int) -> None:
        super().__init__()

        self.frames = frames
        self.frame_index = 0

        self.image = self.frames[self.frame_index]
        self.rect = self.image.get_rect()

        self.previous_time = pygame.time.get_ticks()
        self.set_fps(fps)
    
    def set_fps(self, fps: int) -> None:
        self.frame_duration = 1000 // fps
    
    def update(self) -> None:
        current_time = pygame.time.get_ticks()
        if current_time - self.previous_time >= self.frame_duration:
            self.previous_time = current_time
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            self.image = self.frames[self.frame_index]

class LoadingBar(pygame.sprite.Sprite):
    def __init__(self, size: tuple[int, int], percentage_per_second: float = 1) -> None:
        super().__init__()
        
        self.image = pygame.Surface(size, pygame.SRCALPHA)
        self.rect = self.image.get_rect()

        self.displayed_progress = 0
        self.set_progress(0)
        self.set_percentage_per_second(percentage_per_second)

    def set_percentage_per_second(self, percentage_per_second: float) -> None:
        self.max_progress_change_per_frame = percentage_per_second / FPS

    def set_progress(self, progress: float) -> None:
        self.progress = progress
    
    def get_progress(self) -> float:
        return self.progress
    
    def get_display_progress(self) -> float:
        return self.displayed_progress

    def update(self) -> None:

        self.displayed_progress = min(self.progress, self.displayed_progress + self.max_progress_change_per_frame)

        outer_rect = self.image.get_rect()
        pygame.draw.rect(self.image, (0,0,0,125), outer_rect, border_radius=10)
        pygame.draw.rect(self.image, (255,255,255,255), outer_rect, width=3, border_radius=10)

        inner_rect = outer_rect.inflate(-15, -15)
        inner_rect.width *= self.displayed_progress
        pygame.draw.rect(self.image, (255,255,255,245), inner_rect, border_radius=5)

class LoadingScreen:
    def __init__(self, surface: pygame.Surface, *, _queue: Queue = None, start_progress=0.0, end_progress=1.0) -> None:

        self.surface = surface

        self.start_progress = start_progress
        self.end_progress = end_progress

        if _queue is None:
            self.queue = Queue()
        else:
            self.queue = _queue
        
    def _title_frames(self) -> list[pygame.Surface]:
        frames = []
        size = int(self.surface.get_height() * (2/3))
        for i in range(8):
            frame = pygame.image.load(ASSETS / "TitleSpinner" / f"frame_{i}.webp").convert_alpha()
            frame = pygame.transform.scale(frame, (size, size * frame.get_height() // frame.get_width()))
            frames.append(frame)
        return frames

    def _gradient_surface(self) -> pygame.Surface:
        gradient = pygame.image.load(ASSETS / "VignetteGradientTitle.webp").convert_alpha()
        size = int(self.surface.get_height() * 1.7)
        gradient = pygame.transform.scale(gradient, (size, size))
        return gradient

    def _interpolate_progress(self, progress: float) -> float:
        return self.start_progress + (self.end_progress - self.start_progress) * progress

    def put(self, progress: float) -> None:
        # print(f"Progress: {progress:.2%} on loading screen [{self.start_progress:.2f} - {self.end_progress:.2f}]")
        self.queue.put(self._interpolate_progress(progress))
    
    def run_on_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread
    
    def subsection(self, start_at, end_at) -> "LoadingScreen":
        start_at = self._interpolate_progress(start_at)
        end_at = self._interpolate_progress(end_at)
        return LoadingScreen(self.surface, _queue=self.queue, start_progress=start_at, end_progress=end_at)

    def subsections(self, *subsections: float) -> list["LoadingScreen"]:
        return [self.subsection(start_at, end_at) for start_at, end_at in zip(subsections, subsections[1:] + (1.0,))]

    def run(self) -> bool:
        clock = pygame.time.Clock()


        title_spinner = TitleSpinner(self._title_frames(), 12)
        title_spinner.rect.center = (self.surface.get_width() // 2, self.surface.get_height() // 2)

        loading_bar = LoadingBar((title_spinner.rect.width * 0.9, self.surface.get_height() // 50), percentage_per_second=0.1)
        loading_bar.rect.center = (self.surface.get_width() // 2, int(title_spinner.rect.bottom - title_spinner.rect.height * 0.18))

        gradient = self._gradient_surface()

        font = pygame.font.SysFont("Arial", loading_bar.rect.height // 2, bold=False)

        sprites = pygame.sprite.Group(title_spinner, loading_bar)

        progress = self.start_progress
        loading_bar.set_progress(progress)

        # print(f"Loading screen [{self.start_progress:.2f} - {self.end_progress:.2f}] started.")

        going = True
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

            # text_surface = font.render(f"{progress:.0%}", True, (220,220,255))
            # text_rect = text_surface.get_rect(midtop=loading_bar.rect.midbottom)
            # self.surface.blit(text_surface, text_rect)

            if not self.queue.empty():
                progress = self.queue.get()
                loading_bar.set_progress(progress)

            pygame.display.flip()
            clock.tick(FPS)
        
        # print(f"Loading screen [{self.start_progress:.2f} - {self.end_progress:.2f}] finished.")
        return going
