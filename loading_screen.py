import pathlib
import threading
from queue import Queue

import pygame

import inspect

ASSETS = pathlib.Path("assets")

FPS = 15 # low FPS

class TitleSpinner(pygame.sprite.Sprite):
    def __init__(self, width: int, fps: int) -> None:
        super().__init__()

        self.frames = []
        for i in range(8):
            frame = pygame.image.load(ASSETS / "TitleSpinner" / f"frame_{i}.webp").convert_alpha()
            frame = pygame.transform.scale(frame, (width, width * frame.get_height() // frame.get_width()))
            self.frames.append(frame)

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

class GradientSurface(pygame.sprite.Sprite):
    def __init__(self, size: int) -> None:
        super().__init__()
        
        self.image = pygame.image.load(ASSETS / "VignetteGradientTitle.webp").convert_alpha()
        self.image = pygame.transform.scale(self.image, (size, size))
        self.rect = self.image.get_rect()

class LoadingScreen:

    debug_info = ""

    def __init__(self, surface: pygame.Surface, *, _queue: Queue = None, start_progress=0.0, end_progress=1.0, developer_mode=False) -> None:

        self.surface = surface

        self.start_progress = start_progress
        self.end_progress = end_progress
        self.developer_mode = developer_mode

        if _queue is None:
            self.queue = Queue()
        else:
            self.queue = _queue

    def _interpolate_progress(self, progress: float) -> float:
        return self.start_progress + (self.end_progress - self.start_progress) * progress

    def put(self, progress: float) -> None:
        # print(f"Progress: {progress:.2%} on loading screen [{self.start_progress:.2f} - {self.end_progress:.2f}]")
        self.queue.put(self._interpolate_progress(progress))

        if self.developer_mode:
            frame = inspect.currentframe().f_back
            filename = pathlib.Path(frame.f_code.co_filename).name
            line_number = frame.f_lineno
            func_name = frame.f_code.co_name
            LoadingScreen.debug_info = f"{filename}:{line_number} in {func_name}()"
    
    def run_on_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread
    
    def subsection(self, start_at, end_at) -> "LoadingScreen":
        start_at = self._interpolate_progress(start_at)
        end_at = self._interpolate_progress(end_at)
        return LoadingScreen(self.surface, _queue=self.queue, start_progress=start_at, end_progress=end_at, developer_mode=self.developer_mode)

    def subsections(self, *subsections: float) -> list["LoadingScreen"]:
        return [self.subsection(start_at, end_at) for start_at, end_at in zip(subsections, subsections[1:] + (1.0,))]

    def run(self) -> bool:

        clock = pygame.time.Clock()

        title_spinner = TitleSpinner(int(self.surface.get_height() * (2/3)), 12)
        title_spinner.rect.center = (self.surface.get_width() // 2, self.surface.get_height() // 2)

        loading_bar = LoadingBar((title_spinner.rect.width * 0.9, self.surface.get_height() // 50), percentage_per_second=0.1)
        loading_bar.rect.center = (self.surface.get_width() // 2, int(title_spinner.rect.bottom - title_spinner.rect.height * 0.18))

        gradient = GradientSurface(int(self.surface.get_height() * 1.7))
        gradient.rect.center = (title_spinner.rect.centerx, int(title_spinner.rect.centery - title_spinner.rect.height * 0.13))

        font = pygame.font.SysFont("Arial", loading_bar.rect.height, bold=False)

        sprites = pygame.sprite.Group(gradient, title_spinner, loading_bar)

        progress = self.start_progress
        loading_bar.set_progress(progress)

        # print(f"Loading screen [{self.start_progress:.2f} - {self.end_progress:.2f}] started.")

        debug_display = False
        going = True

        while going and progress < self.end_progress:

            self.surface.fill("black")

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    going = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        going = False
                    else:
                        debug_display = not debug_display
            
            sprites.update()
            sprites.draw(self.surface)

            if debug_display:

                debug_text = font.render(LoadingScreen.debug_info, True, (230,230,255), (0,0,0,150))
                self.surface.blit(debug_text, debug_text.get_rect(midtop=loading_bar.rect.move(0, 5).midbottom))

                fps_text = font.render(f"FPS: {clock.get_fps():.0f}", True, (255,255,255))
                self.surface.blit(fps_text, fps_text.get_rect(topright = self.surface.get_rect().inflate(-20, -20).topright))

                percentage_text = font.render(f"{progress:.1%}", True, (230,230,255), (0,0,0,150))
                self.surface.blit(percentage_text, percentage_text.get_rect(midtop=loading_bar.rect.move(0, percentage_text.get_height() + 10).midbottom))

            if not self.queue.empty():
                progress = self.queue.get()
                loading_bar.set_progress(progress)

            pygame.display.flip()
            clock.tick(FPS)
        
        # print(f"Loading screen [{self.start_progress:.2f} - {self.end_progress:.2f}] finished.")
        return going
