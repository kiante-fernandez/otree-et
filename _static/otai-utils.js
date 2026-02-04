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
        throw new Error('Expected at least ' + expectAtLeast + ' elements matching "' + selector + '", found ' + els.length);
    }
    return els;
}

function eleQuerySelectorStrict(ele, selector) {
    const el = ele.querySelector(selector);
    if (!el) {
        throw new Error('Element matching "' + selector + '" not found');
    }
    return el;
}

function eleQuerySelectorAllStrict(ele, selector, {expectAtLeast = 1} = {}) {
    const els = ele.querySelectorAll(selector);
    if (els.length < expectAtLeast) {
        throw new Error('Expected at least ' + expectAtLeast + ' elements matching "' + selector + '", found ' + els.length);
    }
    return els;
}

function closestStrict(ele, selector) {
    const el = ele.closest(selector);
    if (!el) {
        throw new Error('No ancestor matching "' + selector + '" found');
    }
    return el;
}

// backwards compat
function querySelectorStrict(selector, element = document) {
    const el = element.querySelector(selector);
    if (!el) {
        throw new Error('Element matching "' + selector + '" not found');
    }
    return el;
}
