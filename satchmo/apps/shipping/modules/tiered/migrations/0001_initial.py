# -*- coding: utf-8 -*-
# Generated by Django 1.11.8 on 2017-12-13 13:02
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Carrier',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.SlugField(verbose_name='Key')),
                ('ordering', models.IntegerField(default=0, verbose_name='Ordering')),
                ('active', models.BooleanField(default=True, verbose_name='Active')),
            ],
            options={
                'ordering': ('ordering',),
            },
        ),
        migrations.CreateModel(
            name='CarrierTranslation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('languagecode', models.CharField(choices=[(b'en', b'English')], max_length=10, verbose_name='language')),
                ('name', models.CharField(max_length=50, verbose_name='Carrier')),
                ('description', models.CharField(max_length=200, verbose_name='Description')),
                ('method', models.CharField(help_text='i.e. US Mail', max_length=200, verbose_name='Method')),
                ('delivery', models.CharField(max_length=200, verbose_name='Delivery Days')),
                ('carrier', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='translations', to='tiered.Carrier')),
            ],
            options={
                'ordering': ('languagecode', 'name'),
            },
        ),
        migrations.CreateModel(
            name='ShippingTier',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('min_total', models.DecimalField(decimal_places=2, help_text='The minimum price for this tier to apply', max_digits=10, verbose_name='Min Price')),
                ('price', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Shipping Price')),
                ('expires', models.DateField(blank=True, null=True, verbose_name='Expires')),
                ('carrier', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tiers', to='tiered.Carrier')),
            ],
            options={
                'ordering': ('carrier', 'price'),
            },
        ),
    ]
