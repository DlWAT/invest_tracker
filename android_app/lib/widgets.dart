import 'package:flutter/material.dart';

import 'format.dart';
import 'i18n.dart';
import 'models.dart';

class ListingCard extends StatelessWidget {
  final Listing listing;
  final VoidCallback onTap;
  final VoidCallback? onFavorite;

  const ListingCard({
    super.key,
    required this.listing,
    required this.onTap,
    this.onFavorite,
  });

  @override
  Widget build(BuildContext context) {
    final l = listing;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      clipBehavior: Clip.antiAlias,
      color: const Color(0xFF131a24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: InkWell(
        onTap: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _thumb(l),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          l.title ?? '',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 14, fontWeight: FontWeight.w500),
                        ),
                      ),
                      IconButton(
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                        icon: Icon(
                          l.isFavorite ? Icons.star : Icons.star_border,
                          size: 22,
                          color: l.isFavorite
                              ? const Color(0xFFf5c451)
                              : Colors.grey,
                        ),
                        tooltip: l.isFavorite
                            ? I18n.t('fav_remove')
                            : I18n.t('fav_add'),
                        onPressed: onFavorite,
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    l.locationText ?? l.province ?? '',
                    style: const TextStyle(color: Colors.grey, fontSize: 12),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 12,
                    runSpacing: 4,
                    children: [
                      if (l.beds != null) _spec('${l.beds} ${I18n.t('beds')}'),
                      if (l.baths != null)
                        _spec('${l.baths} ${I18n.t('baths')}'),
                      if (l.areaSqm != null)
                        _spec('${l.areaSqm!.round()} m²'),
                      if (l.pricePerSqm != null)
                        _spec('${l.pricePerSqm!.round()} ₱/m²'),
                    ],
                  ),
                  if (l.hasDrop)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        '${I18n.t('prev_price')} ${fmtPhp(l.pricePrev)}',
                        style: const TextStyle(
                            color: Color(0xFF8a99a8), fontSize: 11),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _spec(String text) => Text(
        text,
        style: const TextStyle(color: Color(0xFFc3cdd7), fontSize: 12),
      );

  Widget _thumb(Listing l) {
    final img = l.thumb;
    return Stack(
      children: [
        AspectRatio(
          aspectRatio: 16 / 10,
          child: img.isNotEmpty
              ? Image.network(
                  img,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => _placeholder(),
                )
              : _placeholder(),
        ),
        Positioned(
          top: 8,
          left: 8,
          child: _badge(l.propertyType ?? I18n.t('type_default'),
              const Color(0xFF10b981)),
        ),
        if (l.isFeatured)
          const Positioned(
            top: 8,
            right: 8,
            child: _badge('★ Featured', Color(0xFFf5c451)),
          ),
        Positioned(
          left: 12,
          bottom: 10,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                fmtPhp(l.pricePhp),
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  shadows: [Shadow(color: Colors.black54, blurRadius: 6)],
                ),
              ),
              Text(
                fmtEur(l.pricePhp),
                style: const TextStyle(fontSize: 11, color: Color(0xFFb9c5cf)),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _placeholder() => Container(
        color: const Color(0xFF0d1219),
        alignment: Alignment.center,
        child: const Icon(Icons.photo, color: Color(0xFF38434f)),
      );

  Widget _badge(String text, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: color.withOpacity(0.9),
          borderRadius: BorderRadius.circular(7),
        ),
        child: Text(
          text,
          style: const TextStyle(
              fontSize: 11, fontWeight: FontWeight.w600, color: Colors.black87),
        ),
      );
}

class PriceChart extends StatelessWidget {
  final List<PricePoint> points;

  const PriceChart({super.key, required this.points});

  @override
  Widget build(BuildContext context) {
    if (points.length < 2) {
      return Container(
        height: 120,
        alignment: Alignment.center,
        child: Text(I18n.t('detail_no_history'),
            style: const TextStyle(color: Colors.grey)),
      );
    }
    return SizedBox(
      height: 180,
      child: CustomPaint(
        painter: _PricePainter(points),
        child: const SizedBox.expand(),
      ),
    );
  }
}

class _PricePainter extends CustomPainter {
  final List<PricePoint> points;

  _PricePainter(this.points);

  @override
  void paint(Canvas canvas, Size size) {
    final prices = points.map((p) => p.pricePhp ?? 0).toList();
    final min = prices.reduce((a, b) => a < b ? a : b);
    final max = prices.reduce((a, b) => a > b ? a : b);
    final span = (max - min) == 0 ? 1.0 : (max - min).toDouble();
    const pad = 20.0;
    final w = size.width - pad * 2;
    final h = size.height - pad * 2;

    Offset to(int i, int price) => Offset(
          pad + w * i / (points.length - 1),
          pad + h * (1 - (price - min) / span),
        );

    final gridPaint = Paint()
      ..color = const Color(0xFF1b2531)
      ..strokeWidth = 1;
    final linePaint = Paint()
      ..color = const Color(0xFF10b981)
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke
      ..strokeJoin = StrokeJoin.round;

    for (int i = 0; i <= 3; i++) {
      final y = pad + h * i / 3;
      canvas.drawLine(Offset(pad, y), Offset(size.width - pad, y), gridPaint);
    }

    final path = Path();
    for (int i = 0; i < prices.length; i++) {
      final o = to(i, prices[i]);
      if (i == 0) {
        path.moveTo(o.dx, o.dy);
      } else {
        path.lineTo(o.dx, o.dy);
      }
    }
    canvas.drawPath(path, linePaint);

    final dotPaint = Paint()..color = const Color(0xFF10b981);
    for (int i = 0; i < prices.length; i++) {
      canvas.drawCircle(to(i, prices[i]), 3.5, dotPaint);
    }

    _label(canvas, fmtPhpShort(max), Offset(2, pad));
    _label(canvas, fmtPhpShort(min), Offset(2, size.height - pad - 12));
  }

  void _label(Canvas canvas, String text, Offset at) {
    final tp = TextPainter(
      text: TextSpan(
          text: text,
          style: const TextStyle(color: Color(0xFF8a99a8), fontSize: 10)),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, at);
  }

  @override
  bool shouldRepaint(covariant _PricePainter old) => old.points != points;
}
