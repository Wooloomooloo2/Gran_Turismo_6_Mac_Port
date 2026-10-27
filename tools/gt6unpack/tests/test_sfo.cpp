// SPDX-License-Identifier: GPL-2.0-only
#include "doctest.h"
#include "pkg_builder.hpp"
#include "sfo.hpp"

using namespace gt6;
using namespace gt6test;

TEST_CASE("parse_sfo reads strings and integers") {
    auto sfo = build_sfo({{"TITLE_ID", "BCES01977"}, {"APP_VER", "01.22"}, {"ATTRIBUTE", "", 0, true}});
    Sfo m = parse_sfo(sfo);
    CHECK(std::get<std::string>(m.at("TITLE_ID")) == "BCES01977");
    CHECK(std::get<std::string>(m.at("APP_VER")) == "01.22");
    CHECK(std::get<uint32_t>(m.at("ATTRIBUTE")) == 0);
}

TEST_CASE("parse_sfo rejects bad input") {
    CHECK_THROWS_AS(parse_sfo(std::vector<uint8_t>{1, 2, 3}), SfoError);
    auto sfo = build_sfo({{"A", "b"}});
    sfo[0] = 'X';
    CHECK_THROWS_AS(parse_sfo(sfo), SfoError);
    auto good = build_sfo({{"A", "b"}});
    good.resize(good.size() - 80);
    CHECK_THROWS_AS(parse_sfo(good), SfoError);
}
