#include "LoadingScreen.h"
#include <iostream>
#include <iomanip>

LoadingScreen::LoadingScreen(double startProgress, double endProgress, bool devMode)
    : startProgress_(startProgress), endProgress_(endProgress), devMode_(devMode) {}

double LoadingScreen::interpolateProgress(double progress) const {
    return startProgress_ + (endProgress_ - startProgress_) * progress;
}

// def put(self, progress, msg=""): (dummy mode branch only)
void LoadingScreen::put(double progress, const std::string& msg) {
    std::cout << "Loading " << std::fixed << std::setprecision(1)
              << (interpolateProgress(progress) * 100.0) << "%: " << msg << "\n";
}

LoadingScreen LoadingScreen::subsection(double startAt, double endAt) const {
    return LoadingScreen(interpolateProgress(startAt), interpolateProgress(endAt), devMode_);
}

std::vector<LoadingScreen> LoadingScreen::subsections(const std::vector<double>& points) const {
    std::vector<double> full = points;
    full.push_back(1.0);
    std::vector<LoadingScreen> result;
    for (size_t i = 0; i + 1 < full.size(); ++i) {
        result.push_back(subsection(full[i], full[i + 1]));
    }
    return result;
}
