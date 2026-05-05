/**
 * Tiny query-selector helpers that throw on miss instead of returning null,
 * so missing DOM elements fail loudly during page wiring.
 */

function docQuerySelectorStrict(selector) {
    const el = document.querySelector(selector);
    if (!el) {
        throw new Error('Element matching "' + selector + '" not found');
    }
    return el;
}

function docQuerySelectorAllStrict(selector, {expectAtLeast = 1} = {}) {
    const els = document.querySelectorAll(selector);
    if (els.length < expectAtLeast) {
        throw new Error(
            'Expected at least ' + expectAtLeast +
            ' elements matching "' + selector + '", found ' + els.length
        );
    }
    return els;
}
