var gulp = require('gulp');

// Plugins
var concat = require('gulp-concat');
var del = require('del');
var git = require('gulp-git');
var install = require('gulp-install');
var path = require('path');
var rename = require('gulp-rename');
var rev = require('gulp-rev');
var shell = require('gulp-shell');
var uglify = require('gulp-uglify');

var npmDependencies = 'package.json';
var jsDependencies = 'bower.json';
var mediaDirectory = 'media/';
var buildDirectory = 'gulp-build/';
var jsBundlesDirectory = mediaDirectory + 'build/js/';
var jsBundles = {
    'main': [
        'lib/front-end/jquery/dist/jquery.js',
        'media/js/components.js',
        'media/js/analytics.js',
        'media/js/main.js',
        'media/js/auth.js',
        'media/js/badges.js'
    ],
    'home': [
        'lib/front-end/OwlCarousel/owl-carousel/owl.carousel.js',
        'media/js/home.js'
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
        'lib/front-end/jquery.hoverIntent-1.5.0/index.js',
        'lib/front-end/jquery.scrollTo-1.4.2/index.js',
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
        'media/js/search.js',
        'media/js/search-navigator.js'
    ],
    'framebuster': [
        'media/js/framebuster.js'
    ],
    'syntax-prism': [
        'lib/front-end/prism/prism.js',
        'media/js/prism-mdn/components/prism-json.js',
        'media/js/prism-mdn/plugins/line-numbering/prism-line-numbering.js',
        'lib/front-end/prism/plugins/line-highlight/prism-line-highlight.js',
        'media/js/syntax-prism.js'
    ],
    'search-suggestions': [
        'media/js/search-suggestions.js'
    ],
    'wiki': [
        'media/js/search-navigator.js',
        'media/js/wiki.js'
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
        'media/js/newsletter.js'
    ],
    'html5shiv': [
        'lib/front-end/html5shiv/dist/html5shiv.js'
    ],
    'jquery.hoverIntent': [
        'lib/front-end/jquery.hoverIntent-1.5.0/index.js'
    ]
};

gulp.task('default', ['compress-javascript', 'build-ckeditor']);

gulp.task('compress-javascript', ['install-javascript-dependencies'], function() {
    // Delete the old bundles and make new ones
    del(jsBundlesDirectory + '*-min-*.js', function() {
        compressBundles(jsBundles, jsBundlesDirectory, '.js');
    });
});

gulp.task('install-javascript-dependencies', function() {
    return gulp.src(jsDependencies)
               .pipe(install());
});

gulp.task('build-ckeditor', function() {
    var ckeBuildDirectory = buildDirectory + 'ckeditor/';
    var ckePlugins = [
        'lib/front-end/ckeditor-plugin-*/**/*',
        'media/js/ckeditor/plugins/*/**/*'
    ];

    // Copy CKEditor to a temporary build directory
    gulp.src('lib/front-end/ckeditor-dev/**/*')
        .pipe(gulp.dest(ckeBuildDirectory))

        // Copy CKEditor plugins to the "plugins" subdirectory
        .on('end', function() {
            gulp.src(ckePlugins)
                .pipe(rename(function(path) {
                    if(path.dirname.indexOf('ckeditor-plugin-') > -1) {
                        path.dirname = path.dirname.replace('ckeditor-plugin-', '')
                    }
                }))
                .pipe(gulp.dest(ckeBuildDirectory + 'plugins'))

                // Build CKEditor
                .on('end', function() {
                    gulp.src('./')
                        .pipe(shell('java -Xmx1024m -jar lib/front-end/ckbuilder-1.7.2/index.jar --build gulp-build/ckeditor cke-build -s --version="4.4.7" --revision affa883 --build-config media/js/ckeditor/config.js --overwrite --no-tar --no-zip'))

                        // Delete the temporary build directory
                        .on('end', function() {
                            del(ckeBuildDirectory);
                        });
                })
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

    // Bower
    gulp.watch(jsDependencies, ['install-javascript-dependencies']);

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
