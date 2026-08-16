#include "BlendModes.h"

namespace BlendModes {

SDL_BlendMode rgbMult() {
    // Verified: SDL's built-in MUL leaves destination alpha untouched,
    // exactly matching pygame.BLEND_RGB_MULT -- and being a built-in
    // (not composed) mode, it's guaranteed supported on every renderer
    // backend, including the software fallback, unlike the custom-
    // composed modes below which require hardware acceleration to
    // actually execute (composing them succeeds even without a GPU, but
    // rendering with them silently no-ops on the software renderer --
    // caught via pixel-level testing in this sandbox, which has no GPU).
    return SDL_BLENDMODE_MUL;
}

SDL_BlendMode rgbaMult() {
    static SDL_BlendMode m = SDL_ComposeCustomBlendMode(
        SDL_BLENDFACTOR_DST_COLOR, SDL_BLENDFACTOR_ZERO, SDL_BLENDOPERATION_ADD,
        SDL_BLENDFACTOR_DST_ALPHA, SDL_BLENDFACTOR_ZERO, SDL_BLENDOPERATION_ADD);
    return m;
}

SDL_BlendMode rgbAdd() {
    // Verified: SDL's built-in ADD leaves destination alpha untouched,
    // matching pygame.BLEND_RGB_ADD -- same portability reasoning as
    // rgbMult() above.
    return SDL_BLENDMODE_ADD;
}

SDL_BlendMode add() {
    static SDL_BlendMode m = SDL_ComposeCustomBlendMode(
        SDL_BLENDFACTOR_ONE, SDL_BLENDFACTOR_ONE, SDL_BLENDOPERATION_ADD,
        SDL_BLENDFACTOR_ONE, SDL_BLENDFACTOR_ONE, SDL_BLENDOPERATION_ADD);
    return m;
}

SDL_BlendMode rgbaSub() {
    static SDL_BlendMode m = SDL_ComposeCustomBlendMode(
        SDL_BLENDFACTOR_ONE, SDL_BLENDFACTOR_ONE, SDL_BLENDOPERATION_REV_SUBTRACT,
        SDL_BLENDFACTOR_ONE, SDL_BLENDFACTOR_ONE, SDL_BLENDOPERATION_REV_SUBTRACT);
    return m;
}

SDL_BlendMode rgbaMax() {
    static SDL_BlendMode m = SDL_ComposeCustomBlendMode(
        SDL_BLENDFACTOR_ONE, SDL_BLENDFACTOR_ONE, SDL_BLENDOPERATION_MAXIMUM,
        SDL_BLENDFACTOR_ONE, SDL_BLENDFACTOR_ONE, SDL_BLENDOPERATION_MAXIMUM);
    return m;
}

SDL_BlendMode rgbMax() {
    static SDL_BlendMode m = SDL_ComposeCustomBlendMode(
        SDL_BLENDFACTOR_ONE, SDL_BLENDFACTOR_ONE, SDL_BLENDOPERATION_MAXIMUM,
        SDL_BLENDFACTOR_ZERO, SDL_BLENDFACTOR_ONE, SDL_BLENDOPERATION_ADD);
    return m;
}

} // namespace BlendModes
