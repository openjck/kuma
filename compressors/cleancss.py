from pipeline.compressors import CompressorBase

class CleanCSSCompressor(CompressorBase):
  def compress_css(self, css):
      return self.execute_command('cleancss', css)
