var gulp = require('gulp');

// Plugins
var concat = require('gulp-concat');
var del = require('del');
var path = require('path');
var rev = require('gulp-rev');
var shell = require('gulp-shell');
var uglify = require('gulp-uglify');

var npmDependencies = 'package.json';
var mediaDirectory = 'media/';
var jsBundlesDirectory = mediaDirectory + 'build/js/';
var jsBundles = {
    'main': [
        'media/js/libs/jquery-2.1.0.js',
        'media/redesign/js/components.js',
        'media/redesign/js/analytics.js',
        'media/redesign/js/main.js',
        'media/redesign/js/auth.js',
        'media/redesign/js/badges.js'
    ],
    'home': [
        'media/js/libs/owl.carousel/owl-carousel/owl.carousel.js',
        'media/redesign/js/home.js'
    ],
    'popup': [
        'media/js/libs/jquery-ui-1.10.3.custom/js/jquery-ui-1.10.3.custom.min.js',
        'media/js/modal-control.js'
    ],
    'profile': [
        'media/js/profile.js',
        'media/js/moz-jquery-plugins.js'
    ],
    'events': [
        'media/js/libs/jquery.gmap-1.1.0.js',
        'media/js/calendar.js'
    ],
    'demostudio': [
        'media/js/libs/jquery.hoverIntent.minified.js',
        'media/js/libs/jquery.scrollTo-1.4.2-min.js',
        'media/js/demos.js',
        'media/js/libs/jquery-ui-1.10.3.custom/js/jquery-ui-1.10.3.custom.min.js',
        'media/js/modal-control.js'
    ],
    'demostudio_devderby_landing': [
        'media/js/demos-devderby-landing.js'
    ],
    'jquery-ui': [
        'media/js/libs/jquery-ui-1.10.3.custom/js/jquery-ui-1.10.3.custom.min.js',
        'media/js/moz-jquery-plugins.js'
    ],
    'tagit': [
        'media/js/libs/tag-it.js'
    ],
    'search': [
        'media/redesign/js/search.js',
        'media/redesign/js/search-navigator.js'
    ],
    'framebuster': [
        'media/js/framebuster.js'
    ],
    'syntax-prism': [
        'media/js/libs/prism/prism.js',
        'media/js/prism-mdn/components/prism-json.js',
        'media/js/prism-mdn/plugins/line-numbering/prism-line-numbering.js',
        'media/js/libs/prism/plugins/line-highlight/prism-line-highlight.js',
        'media/js/syntax-prism.js'
    ],
    'search-suggestions': [
        'media/js/search-suggestions.js'
    ],
    'wiki': [
        'media/redesign/js/search-navigator.js',
        'media/redesign/js/wiki.js'
    ],
    'wiki-edit': [
        'media/js/wiki-edit.js',
        'media/js/libs/tag-it.js',
        'media/js/wiki-tags-edit.js'
    ],
    'wiki-move': [
        'media/js/wiki-move.js'
    ],
    'newsletter': [
        'media/redesign/js/newsletter.js'
    ],
};

gulp.task('default', ['compress-javascript']);

gulp.task('compress-javascript', function() {
    // Delete the old bundles and make new ones
    del(jsBundlesDirectory + '*-min-*.js', function() {
        compressBundles(jsBundles, jsBundlesDirectory, '.js');
    });
});

/**
 * Install any new requirements that were added to package.json and remove any
 * requirements that are no longer mentioned, updating npm-shrinkwrap.json in
 * the process.
 *
 * In other words, update node_modules and npm-shrinkwrap.json to reflect the
 * current state of package.json.
 */
gulp.task('install-and-shrinkwrap-npm-dependencies', function() {
    // There are Gulp plugins for some of these steps, but they don't work well
    // together, so shell commands are used instead.
    del('npm-shrinkwrap.json', function() {
        gulp.src(npmDependencies)
            .pipe(shell(['npm prune']))
            .pipe(shell(['npm install']))
            .pipe(shell(['npm shrinkwrap --dev']));
    });
});

gulp.task('watch', function() {
    // NPM
    gulp.watch(npmDependencies, ['install-and-shrinkwrap-npm-dependencies']);

    // JavaScript bundles
    for(var bundleName in jsBundles) {
        if(jsBundles.hasOwnProperty(bundleName)) {
            var bundle = jsBundles[bundleName];
            watchJSBundle(bundleName, bundle);
        }
    }

    /*
     * This needs to be written outside the for loop to work as expected.
     * https://jslinterrors.com/dont-make-functions-within-a-loop
     */
    function watchJSBundle(bundleName, bundle) {
        gulp.watch(bundle, function() {

            // Delete the old bundle and make a new one
            del(jsBundlesDirectory + bundleName + '-min-*.js', function() {
                compressBundle(bundleName, bundle, jsBundlesDirectory, '.js');
            });

        });
    }
});

function compressBundle(bundleName, bundle, destination, extension) {
    var bundleObject = {};
    bundleObject[bundleName] = bundle;

    compressBundles(bundleObject, destination, extension);
}

/**
 * Compress bundles one-by-one and revision them.
 *
 * By compressing bundles one-by-one, rather than asynchronously, we can know
 * when compression has completed and only begin revisioning at that time.
 */
function compressBundles(bundles, destination, extension) {
    // All bundles have been compressed. Revision them.
    if(Object.keys(bundles).length === 0) {
        var compressedBundles = destination + '*-min' + extension;
        return gulp.src(compressedBundles, { base: path.join(process.cwd(), mediaDirectory) } ) // https://github.com/sindresorhus/gulp-rev/issues/83
                   .pipe(rev())
                   .pipe(gulp.dest(mediaDirectory))
                   .pipe(rev.manifest(mediaDirectory + 'rev-manifest.json', { merge: true, base: mediaDirectory })) // https://github.com/sindresorhus/gulp-rev/issues/54#issuecomment-53123997
                   .pipe(gulp.dest(mediaDirectory))
                   .on('end', function() {
                       del(compressedBundles);
                   });
    }

    // Not all bundles have been compressed. Compress the next one and recurse.
    else {
        var nextBundleName = Object.keys(bundles)[0];
        var nextBundle = bundles[nextBundleName];

        gulp.src(nextBundle)
            .pipe(concat(nextBundleName + '-min' + extension))
            .pipe(uglify())
            .pipe(gulp.dest(destination))
            .on('end', function() {
                delete bundles[nextBundleName];
                compressBundles(bundles, destination, extension);
            });
    }
}
