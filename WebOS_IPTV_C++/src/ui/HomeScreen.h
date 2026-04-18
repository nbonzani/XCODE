#pragma once
// Catalog home screen — tabs (Films / Séries / Favoris) + poster grid + sidebar of categories.
// Keeps two PosterGrid instances alive, swaps which one is visible on tab change.

#include <functional>
#include <memory>
#include <string>
#include <vector>

struct SDL_Renderer;

namespace iptv::store { class Cache; }

namespace iptv::ui {

class FocusManager;
class ImageLoader;
class TextRenderer;
class PosterGrid;

class HomeScreen {
public:
    HomeScreen(TextRenderer& text, FocusManager& focus, ImageLoader& images, store::Cache& cache);
    ~HomeScreen();

    enum class Tab { Movies, Series, Favorites };

    void load();                          // populate grids from cache
    void handleKey(int code, bool& handled);
    void render(SDL_Renderer* r, int winW, int winH);

    void setOnOpenMovie(std::function<void(const std::string& streamId)> cb) { on_movie_ = std::move(cb); }
    void setOnOpenSeries(std::function<void(const std::string& seriesId)> cb) { on_series_ = std::move(cb); }
    void setOnOpenSettings(std::function<void()> cb) { on_settings_ = std::move(cb); }

private:
    void switchTab(Tab t);

    TextRenderer& text_;
    FocusManager& focus_;
    ImageLoader&  images_;
    store::Cache& cache_;

    Tab tab_ = Tab::Movies;
    std::unique_ptr<PosterGrid> gridMovies_;
    std::unique_ptr<PosterGrid> gridSeries_;
    std::unique_ptr<PosterGrid> gridFavorites_;

    std::function<void(const std::string&)> on_movie_;
    std::function<void(const std::string&)> on_series_;
    std::function<void()>                   on_settings_;
};

}  // namespace iptv::ui
