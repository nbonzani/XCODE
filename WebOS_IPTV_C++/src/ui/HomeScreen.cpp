#include "ui/HomeScreen.h"

#include <SDL2/SDL.h>

#include "app/KeyCodes.h"
#include "store/Cache.h"
#include "store/Favorites.h"
#include "ui/FocusManager.h"
#include "ui/ImageLoader.h"
#include "ui/PosterGrid.h"
#include "ui/TextRenderer.h"

namespace iptv::ui {

namespace {
constexpr int kGridX = 60;
constexpr int kGridY = 160;
constexpr int kGridW = 1800;
constexpr int kGridH = 860;
}

HomeScreen::HomeScreen(TextRenderer& t, FocusManager& f, ImageLoader& il, store::Cache& c)
    : text_(t), focus_(f), images_(il), cache_(c) {
    gridMovies_    = std::make_unique<PosterGrid>(focus_, images_, text_);
    gridSeries_    = std::make_unique<PosterGrid>(focus_, images_, text_);
    gridFavorites_ = std::make_unique<PosterGrid>(focus_, images_, text_);
    for (auto* g : {gridMovies_.get(), gridSeries_.get(), gridFavorites_.get()}) {
        g->setBounds(kGridX, kGridY, kGridW, kGridH);
        g->setColumns(6);
        g->setCellSize(280, 420);
        g->setGap(16);
    }
}

HomeScreen::~HomeScreen() = default;

void HomeScreen::load() {
    auto snap = cache_.loadCatalog();

    std::vector<GridItem> movies;
    movies.reserve(snap.movies.size());
    for (const auto& m : snap.movies) {
        movies.push_back({m.stream_id, m.name, ""});
    }

    std::vector<GridItem> series;
    series.reserve(snap.series.size());
    for (const auto& s : snap.series) {
        series.push_back({s.series_id, s.name, s.cover});
    }

    // Favorites from JSON file.
    auto favs = store::Favorites::all();
    std::vector<GridItem> favoritesGrid;
    for (const auto& m : favs["movies"]) {
        GridItem it;
        it.id    = m.value("stream_id", std::string{});
        it.title = m.value("name",      std::string{});
        it.imageUrl = m.value("stream_icon", std::string{});
        if (!it.id.empty()) favoritesGrid.push_back(std::move(it));
    }
    for (const auto& s : favs["series"]) {
        GridItem it;
        it.id    = s.value("series_id", std::string{});
        it.title = s.value("name",      std::string{});
        it.imageUrl = s.value("cover",  std::string{});
        if (!it.id.empty()) favoritesGrid.push_back(std::move(it));
    }

    // Poster URLs from Xtream aren't stored in Cache directly in this MVP, so movie
    // posters use placeholders. Series covers + favorites carry their raw URL.
    focus_.clear();
    gridMovies_->setItems(std::move(movies));
    gridMovies_->setOnSelect([this](const GridItem& i){ if (on_movie_) on_movie_(i.id); });

    gridSeries_->setItems(std::move(series));
    gridSeries_->setOnSelect([this](const GridItem& i){ if (on_series_) on_series_(i.id); });

    gridFavorites_->setItems(std::move(favoritesGrid));
    gridFavorites_->setOnSelect([this](const GridItem& i){
        // Favorites may be either movies or series — we only know movie ids are in stream_id.
        // MVP: try movie first, caller can discriminate via id format if needed.
        if (on_movie_) on_movie_(i.id);
    });

    switchTab(tab_);
}

void HomeScreen::switchTab(Tab t) {
    tab_ = t;
    focus_.clear();
    PosterGrid* grid = gridMovies_.get();
    if (tab_ == Tab::Series)    grid = gridSeries_.get();
    if (tab_ == Tab::Favorites) grid = gridFavorites_.get();
    // Re-register grid focus nodes by calling setItems with unchanged items would be
    // wasteful — the grid re-registers focus on setItems(). For tab switches we rely on
    // the grid keeping its internal state and calling registerFocus implicitly.
    grid->prefetchVisible();
}

void HomeScreen::handleKey(int code, bool& handled) {
    handled = true;
    if (code == app::KEY::RED)    { switchTab(Tab::Movies);    return; }
    if (code == app::KEY::GREEN)  { switchTab(Tab::Series);    return; }
    if (code == app::KEY::YELLOW) { switchTab(Tab::Favorites); return; }
    if (code == app::KEY::BLUE)   { if (on_settings_) on_settings_(); return; }

    if (code == app::KEY::UP)    { focus_.moveUp();    return; }
    if (code == app::KEY::DOWN)  { focus_.moveDown();  return; }
    if (code == app::KEY::LEFT)  { focus_.moveLeft();  return; }
    if (code == app::KEY::RIGHT) { focus_.moveRight(); return; }
    if (app::isOkKey(code))      { focus_.activate();  return; }

    handled = false;
}

void HomeScreen::render(SDL_Renderer* r, int winW, int winH) {
    SDL_SetRenderDrawColor(r, 12, 12, 16, 255);
    SDL_RenderClear(r);

    text_.draw("IPTV Native", 60, 40, {240, 240, 240, 255});

    // Tab bar
    const char* labels[3] = {"[ROUGE] Films", "[VERT] Séries", "[JAUNE] Favoris"};
    Tab tabs[3] = {Tab::Movies, Tab::Series, Tab::Favorites};
    int x = 60;
    for (int i = 0; i < 3; ++i) {
        Color c = (tab_ == tabs[i]) ? Color{240, 240, 240, 255} : Color{130, 130, 140, 255};
        text_.draw(labels[i], x, 110, c);
        int w = 0, h = 0; text_.measure(labels[i], w, h);
        x += w + 40;
    }
    text_.draw("[BLEU] Configuration", winW - 380, 110, {130, 130, 140, 255});

    PosterGrid* grid = gridMovies_.get();
    if (tab_ == Tab::Series)    grid = gridSeries_.get();
    if (tab_ == Tab::Favorites) grid = gridFavorites_.get();

    grid->ensureFocusedVisible();
    grid->prefetchVisible();
    grid->render(r, focus_.focused());

    (void)winH;
}

}  // namespace iptv::ui
