import pathlib
import time
import multiprocessing
from multiprocessing import synchronize
import config

import pygame

ASSETS = pathlib.Path("loading_assets")
GAME_ASSETS = pathlib.Path("assets")

FPS = 24 # double animation time

class UserQuitDuringLoadingException(Exception):
    pass

class LoadingScreen:

    debug_info = ""

    def __init__(self, *, _queue: multiprocessing.Queue = None, _has_quit_event: synchronize.Event = None,
                  start_progress=0.0, end_progress=1.0, dev_mode=False) -> None:

        self.start_progress = start_progress
        self.end_progress = end_progress
        self.dev_mode = dev_mode

        if (_queue is None or _has_quit_event is None):
            self.queue = multiprocessing.Queue()
            self.has_quit_event = multiprocessing.Event()
        else:
            self.queue = _queue
            self.has_quit_event = _has_quit_event

    def _interpolate_progress(self, progress: float) -> float:
        return self.start_progress + (self.end_progress - self.start_progress) * progress

    def put(self, progress: float, msg: str = "") -> None:    
        if self.is_quit():
            raise UserQuitDuringLoadingException("Loading screen has been quit.")
        self.queue.put((self._interpolate_progress(progress), msg))

    def is_quit(self) -> bool:
        return self.has_quit_event.is_set()

    def subsection(self, start_at, end_at) -> "LoadingScreen":
        start_at = self._interpolate_progress(start_at)
        end_at = self._interpolate_progress(end_at)
        return LoadingScreen(_queue=self.queue, _has_quit_event=self.has_quit_event, start_progress=start_at, end_progress=end_at, dev_mode=self.dev_mode)

    def subsections(self, *subsections: float) -> list["LoadingScreen"]:
        return [self.subsection(start_at, end_at) for start_at, end_at in zip(subsections, subsections[1:] + (1.0,))]
    
    def run(self):

        pygame.init()

        window = pygame.display.set_mode((0,0))

        pygame.display.set_caption(config.WINDOW_NAME)
        pygame.display.set_icon(pygame.image.load(config.WINDOW_ICON_PATH))

        going = self._run(window)
        if not going:
            self.has_quit_event.set()
        pygame.quit()

    def _run(self, surface: pygame.Surface) -> bool:
        clock = pygame.time.Clock()

        title_spinner_frames = [pygame.image.load(ASSETS / f"frame_{i}.webp") for i in range(1, 8)]
        title_spinner = Animation(title_spinner_frames, int(surface.get_height() * (2/3)), 12)
        title_spinner.rect.center = (surface.get_width() // 2, surface.get_height() // 2)

        loading_bar = LoadingBar((title_spinner.rect.width * 0.9, surface.get_height() // 50), percentage_per_second=0.25)
        loading_bar.rect.center = (surface.get_width() // 2, int(title_spinner.rect.bottom - title_spinner.rect.height * 0.18))

        gradient = GradientSurface(int(surface.get_height() * 1.7))
        gradient.rect.center = (title_spinner.rect.centerx, int(title_spinner.rect.centery - title_spinner.rect.height * 0.13))

        font = pygame.font.SysFont("Arial", loading_bar.rect.height, bold=False)

        sprites = pygame.sprite.Group(gradient, title_spinner, loading_bar)

        show_debug_display = self.dev_mode
        progress = self.start_progress

        debug_message = ""

        loading_bar.set_progress(progress)

        going = True

        start = time.time()

        while going and progress < self.end_progress:

            surface.fill("black")

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    going = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        going = False
                    elif event.key in (pygame.K_SPACE, pygame.K_F3):
                        show_debug_display = not show_debug_display
                    elif event.key == pygame.K_m:
                        pygame.display.iconify()

            sprites.update()
            sprites.draw(surface)

            if show_debug_display:

                fps_text = font.render(f"FPS: {clock.get_fps():.0f}", True, (255,255,255))
                surface.blit(fps_text, fps_text.get_rect(topright=surface.get_rect().inflate(-20, -20).topright))

                debug_text = font.render(debug_message, True, (230,230,255), (0,0,0,150))
                surface.blit(debug_text, (10, 10))

                percentage_text = font.render(f"{progress:.1%}", True, (230,230,255), (0,0,0,150))
                surface.blit(percentage_text, (10, 50))

                time_text = font.render(f"{time.time() - start:.1f} seconds...", True, (230,230,255), (0,0,0,150))
                surface.blit(time_text, (10, 90))

            if not self.queue.empty():
                progress, debug_message = self.queue.get()
                loading_bar.set_progress(progress)

            pygame.display.flip()
            clock.tick(FPS)
        
        # print(f"Loading screen [{self.start_progress:.2f} - {self.end_progress:.2f}] finished.")
        return going

class Animation(pygame.sprite.Sprite):
    def __init__(self, frames: list[pygame.Surface], width: int, fps: int) -> None:
        super().__init__()

        self.frames: list[pygame.Surface] = [
            pygame.transform.scale(frame, (width, width * frame.get_height() // frame.get_width())).convert_alpha() for frame in frames
        ]

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

    def set_progress(self, progress: float, force_display: bool = False) -> None:
        self.progress = progress
        if force_display:
            self.displayed_progress = progress

    def get_progress(self) -> float:
        return self.progress

    def get_display_progress(self) -> float:
        return self.displayed_progress

    def update(self) -> None:

        self.displayed_progress = min(self.progress, self.displayed_progress + self.max_progress_change_per_frame)

        outer_rect = self.image.get_rect()
        pygame.draw.rect(self.image, (0,0,0,125), outer_rect, border_radius=10)
        pygame.draw.rect(self.image, (255,255,255,255), outer_rect, width=2, border_radius=10)

        inner_rect = outer_rect.inflate(-10, -10)
        inner_rect.width *= self.displayed_progress
        pygame.draw.rect(self.image, (255,255,255,245), inner_rect, border_radius=5)

class GradientSurface(pygame.sprite.Sprite):
    def __init__(self, size: int) -> None:
        super().__init__()
        
        self.image = pygame.image.load(ASSETS / "VignetteGradientTitle.webp").convert_alpha()
        self.image = pygame.transform.scale(self.image, (size, size))
        self.rect = self.image.get_rect()