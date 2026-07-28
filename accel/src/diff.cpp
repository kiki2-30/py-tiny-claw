// accel/src/diff.cpp —— 逐行去缩进匹配（对标 Python 4 层退化）
// C++ 优势：ltrim 零堆分配 vs Python strip() 每次创建新字符串

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <string>
#include <vector>
#include <stdexcept>

namespace py = pybind11;

struct DiffResult { int start, end; };

static std::string ltrim(const std::string& s) {
    size_t i = 0;
    while (i < s.size() && (s[i] == ' ' || s[i] == '\t')) i++;
    return s.substr(i);
}

DiffResult fuzzy_locate(const std::string& content, const std::string& old_text) {
    if (old_text.empty())
        throw std::invalid_argument("old_text empty");

    // L1: exact
    size_t pos = content.find(old_text);
    if (pos != std::string::npos) {
        size_t n2 = content.find(old_text, pos + 1);
        if (n2 == std::string::npos)
            return {int(pos), int(pos + old_text.size())};
        throw std::runtime_error("old_text matched multiple times");
    }

    // L2: normalize \r\n
    std::string nc = content, no = old_text;
    for (size_t p; (p = nc.find("\r\n")) != std::string::npos; ) nc.replace(p, 2, "\n");
    for (size_t p; (p = no.find("\r\n")) != std::string::npos; ) no.replace(p, 2, "\n");
    pos = nc.find(no);
    if (pos != std::string::npos) {
        size_t n2 = nc.find(no, pos + 1);
        if (n2 == std::string::npos) return {int(pos), int(pos + no.size())};
    }

    // L3: trim
    std::string t = no;
    while (!t.empty() && (t.front() == ' ' || t.front() == '\n')) t.erase(0, 1);
    while (!t.empty() && (t.back() == ' ' || t.back() == '\n')) t.pop_back();
    if (!t.empty() && t != no) {
        pos = nc.find(t);
        if (pos != std::string::npos) {
            size_t n2 = nc.find(t, pos + 1);
            if (n2 == std::string::npos) return {int(pos), int(pos + t.size())};
        }
    }

    // L4: line-by-line with ltrim
    std::vector<std::string> cl, ol;
    size_t s = 0;
    for (size_t i = 0; i <= nc.size(); i++)
        if (i == nc.size() || nc[i] == '\n') { cl.push_back(nc.substr(s, i-s)); s = i+1; }
    s = 0;
    for (size_t i = 0; i <= no.size(); i++)
        if (i == no.size() || no[i] == '\n') { ol.push_back(no.substr(s, i-s)); s = i+1; }
    if (ol.empty() || cl.size() < ol.size())
        throw std::runtime_error("old_text not found");

    for (size_t i = 0; i + ol.size() <= cl.size(); i++) {
        bool ok = true;
        for (size_t j = 0; j < ol.size(); j++)
            if (ltrim(cl[i+j]) != ltrim(ol[j])) { ok = false; break; }
        if (ok) {
            int bs = 0;
            for (size_t k = 0; k < i; k++) bs += cl[k].size() + 1;
            int be = bs;
            for (size_t k = 0; k < ol.size(); k++) be += cl[i+k].size() + 1;
            return {bs, be - 1};
        }
    }
    throw std::runtime_error("old_text not found");
}

PYBIND11_MODULE(_diff, m) {
    py::class_<DiffResult>(m, "DiffResult")
        .def_readonly("start", &DiffResult::start)
        .def_readonly("end", &DiffResult::end);
    m.def("fuzzy_locate", &fuzzy_locate);
}
