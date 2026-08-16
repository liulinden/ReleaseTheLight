#pragma once
#include <string>
#include <vector>
#include <stdexcept>

// Ported from loading_screen.py.
//
// FLAGGED SCOPE DECISION: only "dummy mode" is implemented here (progress
// printed to console) -- the real mode opens a SEPARATE process with its
// own pygame window (spinner animation, progress bar, gradient
// background), communicating via multiprocessing.Queue + Event. That
// needs: a second SDL window, cross-process (or cross-thread) IPC, and
// three small sprite-animation classes (TitleSpinner/LoadingBar/
// GradientSurface) that exist purely for that loading UI and aren't used
// anywhere else in the game.
//
// This is a real scope cut, not a silent one: the Python's own main.py
// has a commented-out dummy-mode line (`# loading_screen = LoadingScreen(
// dev_mode=config.DEV_MODE, dummy_mode=True)`), confirming dummy mode is
// an intentionally-supported, first-class path in the original -- not
// something invented for this port. Given world generation completes in
// single-digit milliseconds in this port (verified: ~3ms for a full
// world, vs. whatever prompted a loading screen for the Python original),
// a real windowed loading screen has much less practical value here.
// The real windowed mode could be added later without changing this
// class's public interface (put/subsection/subsections/isQuit all stay
// the same either way).
class UserQuitDuringLoadingError : public std::runtime_error {
public:
    explicit UserQuitDuringLoadingError(const std::string& msg) : std::runtime_error(msg) {}
};

class LoadingScreen {
public:
    // was: def __init__(self, *, _queue=None, _has_quit_event=None,
    //                    start_progress=0.0, end_progress=1.0,
    //                    dev_mode=False, dummy_mode=False)
    // dummy_mode is not a parameter here -- it's the only mode implemented.
    explicit LoadingScreen(double startProgress = 0.0, double endProgress = 1.0, bool devMode = false);

    // was: def put(self, progress, msg="")
    void put(double progress, const std::string& msg = "");

    // was: def is_quit(self) -- dummy mode never quits early (no window,
    // no way for the user to signal quit through this object specifically).
    bool isQuit() const { return false; }

    // was: def subsection(self, start_at, end_at)
    LoadingScreen subsection(double startAt, double endAt) const;

    // was: def subsections(self, *subsections) -- takes N breakpoints,
    // returns N subsections (implicitly closing the last range at 1.0,
    // matching `subsections[1:] + (1.0,)`).
    std::vector<LoadingScreen> subsections(const std::vector<double>& points) const;

private:
    double interpolateProgress(double progress) const;

    double startProgress_, endProgress_;
    bool devMode_;
};
