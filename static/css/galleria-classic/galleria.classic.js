Galleria.themes.create({
    name: 'classic',
    author: 'Galleria',
    version: '1.1',
    css: 'galleria.classic.css',
    defaults: {
        transition: 'slide'
    },
    init: function(options) {

        this.$('loader').show().fadeTo(200, .4);
        this.$('counter').show().fadeTo(200, .4);

        this.$('thumbnails').children().hover(function() {
            $(this).not('.active').fadeTo(200, 1);
        }, function() {
            $(this).not('.active').fadeTo(400, .4);
        }).not('.active').css('opacity',.4);

        this.$('container').hover(this.proxy(function() {
            this.$('image-nav-left,image-nav-right,counter').fadeIn(200);
        }), this.proxy(function() {
            this.$('image-nav-left,image-nav-right,counter').fadeOut(500);
        }));

        this.$('image-nav-left,image-nav-right,counter').hide();

        this.$('info-link,info-close,info-text').show();

        this.bind(Galleria.LOADSTART, function(e) {
            if (!e.cached) {
                this.$('loader').show().fadeTo(200, .4);
            }
            if (this.hasInfo()) {
                this.$('info').show();
            } else {
                this.$('info').hide();
            }
            $(e.thumbTarget).parent().addClass('active').css('opacity',1)
                .siblings('.active').removeClass('active').fadeTo(400,.4);
        });

        this.bind(Galleria.LOADFINISH, function(e) {
            this.$('loader').fadeOut(200);
            $(e.thumbTarget).css('opacity',1)
        });
    }
});
