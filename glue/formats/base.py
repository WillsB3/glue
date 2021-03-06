import os
import json
import codecs
import plistlib
import textwrap

from jinja2 import Template

from glue.helpers import round_up, nearest_fration
from glue import __version__


class BaseFormat(object):

    extension = None
    build_per_ratio = False

    def __init__(self, sprite):
        self.sprite = sprite

    def output_dir(self, *args, **kwargs):
        return self.sprite.config['{0}_dir'.format(self.format_label)]

    def output_filename(self, ratio=None, *args, **kwargs):
        if self.build_per_ratio:
            if ratio is None:
                raise AttributeError("Format {0} output_filename requires a ratio.".format(self.__class__))
            ratio_suffix = '@%.1fx' % ratio if int(ratio) != ratio else '@%ix' % ratio
            if ratio_suffix == '@1x':
                ratio_suffix = ''
            return '{0}{1}'.format(self.sprite.name, ratio_suffix)
        return self.sprite.name

    def output_path(self, *args, **kwargs):
        return os.path.join(self.output_dir(*args, **kwargs), '{0}.{1}'.format(self.output_filename(*args, **kwargs), self.extension))

    def build(self):
        if self.build_per_ratio:
            for ratio in self.sprite.config['ratios']:
                self.save(ratio=ratio)
        else:
            self.save()

    def save(self, *args, **kwargs):
        raise NotImplementedError

    def needs_rebuild(self):
        return True

    def validate(self):
        pass

    @property
    def format_label(self):
        from glue.formats import formats
        return dict((v,k) for k, v in formats.iteritems())[self.__class__]

    @classmethod
    def populate_argument_parser(cls, parser):
        pass

    @classmethod
    def apply_parser_contraints(cls, parser, options):
        pass

    def scale_down(self, value, ratio):
        return round_up(value / ratio)


class BaseTextFormat(BaseFormat):

    def get_context(self, *args, **kwargs):
        sprite_path = os.path.relpath(self.sprite.sprite_path(), self.output_dir())
        context = {'version': __version__,
                   'hash': self.sprite.hash,
                   'name': self.sprite.name,
                   'sprite_path': sprite_path,
                   'sprite_filename': os.path.basename(sprite_path),
                   'width': int(self.sprite.canvas_size[0] / self.sprite.max_ratio),
                   'height': int(self.sprite.canvas_size[1] / self.sprite.max_ratio),
                   'images': [],
                   'ratios': {}}

        for i, img in enumerate(self.sprite.images):
            image = dict(filename=img.filename,
                         last=i == len(self.sprite.images) - 1,
                         x=round_up((img.x * -1 - img.margin[3] * self.sprite.max_ratio) / self.sprite.max_ratio),
                         y=round_up((img.y * -1 - img.margin[0] * self.sprite.max_ratio) / self.sprite.max_ratio),
                         abs_x=round_up((img.x + img.margin[3] * self.sprite.max_ratio) / self.sprite.max_ratio),
                         abs_y=round_up((img.y + img.margin[0] * self.sprite.max_ratio) / self.sprite.max_ratio),
                         height=round_up((img.height / self.sprite.max_ratio) + img.padding[0] + img.padding[2]),
                         width=round_up((img.width / self.sprite.max_ratio) + img.padding[1] + img.padding[3]),
                         original_width=img.original_width,
                         original_height=img.original_height,
                         ratios={})

            for r in self.sprite.ratios:
                image['ratios'][r] = dict(filename=img.filename,
                                          last=i == len(self.sprite.images) - 1,
                                          x=round_up((image['x'] / self.sprite.max_ratio) * r),
                                          y=round_up((image['y'] / self.sprite.max_ratio) * r),
                                          abs_x=round_up((image['abs_x'] / self.sprite.max_ratio) * r),
                                          abs_y=round_up((image['abs_y'] / self.sprite.max_ratio) * r),
                                          height=round_up((image['height'] / self.sprite.max_ratio) * r),
                                          width=round_up((image['width'] / self.sprite.max_ratio) * r))

            context['images'].append(image)

        # Ratios
        for r in self.sprite.ratios:
            ratio_sprite_path = os.path.relpath(self.sprite.sprite_path(ratio=r), self.output_dir())
            context['ratios'][r] = dict(ratio=r,
                                        fraction=nearest_fration(r),
                                        sprite_path=ratio_sprite_path,
                                        sprite_filename=os.path.basename(ratio_sprite_path),
                                        width=int(self.sprite.canvas_size[0] / r),
                                        height=int(self.sprite.canvas_size[1] / r))

        return context

    def render(self, *args, **kwargs):
        raise NotImplementedError

    def save(self, *args, **kwargs):
        # Create the destination directory if required
        if not os.path.exists(self.output_dir(*args, **kwargs)):
            os.makedirs(self.output_dir(*args, **kwargs))

        with codecs.open(self.output_path(*args, **kwargs), 'w', 'utf-8-sig') as f:
            f.write(self.render(*args, **kwargs))


class BaseJSONFormat(BaseTextFormat):

    meta_key = 'meta'

    def needs_rebuild(self):
        for ratio in self.sprite.config['ratios']:
            json_path = self.output_path(ratio)
            if os.path.exists(json_path):
                with codecs.open(json_path, 'r', 'utf-8-sig') as f:
                    try:
                        data = json.loads(f.read())
                        assert data[self.meta_key]['hash'] == self.sprite.hash
                    except Exception:
                        continue
            return True
        return False

    def render(self, *args, **kwargs):
        return json.dumps(self.get_context(*args, **kwargs))


class BasePlistFormat(BaseTextFormat):

    meta_key = 'metadata'

    def render(self, *args, **kwargs):
        context = self.get_context(*args, **kwargs)
        return plistlib.writePlistToString(context)

    def needs_rebuild(self):
        for ratio in self.sprite.config['ratios']:
            cocos2d_path = self.output_path(ratio)
            if os.path.exists(cocos2d_path):
                try:
                    data = plistlib.readPlist(cocos2d_path)
                    assert data[self.meta_key]['hash'] == self.sprite.hash
                except Exception:
                    continue
            return True
        return False


class JinjaTextFormat(BaseTextFormat):

    template = ''

    def render(self, *args, **kwargs):
        context = self.get_context(*args, **kwargs)
        template = self.template
        custom_template_config = '{0}_template'.format(self.format_label)
        if self.sprite.config.get(custom_template_config):
            with open(self.sprite.config[custom_template_config]) as f:
                template = f.read()
        return Template(textwrap.dedent(template).strip()).render(**context)
