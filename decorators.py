# -*- mode: python; coding: utf-8; -*-
from django.db import models
from django.db.models.query import QuerySet
from django.conf import settings

def _key(obj, field):
    return '%s:%s:%s' % (obj.__class__.__name__.lower(),field, obj.pk, )

class IncrementalQuerySet(QuerySet):
    """
    QuerySet for wrapping default results and perform extra actions with them.
    """

    def __init__(self, *args, **kwargs):
        super(IncrementalQuerySet, self).__init__(*args, **kwargs)
        self._modify_funcs = []
        self._decorate_funcs = []

    def _clone(self, klass=None, setup=False, **kw):
        c = super(IncrementalQuerySet, self)._clone(klass, setup, **kw)
        c._decorate_funcs = self._decorate_funcs[:]
        return c


    def decorate(self, fn):
        """
        Register a function which will decorate a retrieved object before it's returned.
        """
        if fn not in self._decorate_funcs:
            self._decorate_funcs.append(fn)
        return self

    def modify(self, fn):
        if fn not in self._modify_funcs:
            self._modify_funcs.append(fn)
            
        print self._modify_funcs
        return self

    def add_increments(self,object_list):
        '''
        Adds incremental values from cache
        '''
        actual_list, keys = [], set()
        
        for obj in object_list: 
            for field in obj.__class__.incremental:
                keys.add(_key(obj, field))
            actual_list.append(obj)

        if not keys:
            return []

        cached = dict(zip(keys, settings.REDIS.mget(*keys)))

        for obj in actual_list:
            for field in obj.__class__.incremental:
                old_attr = getattr(obj, field, 0)
                cached_value = cached.get(_key(obj, field)) or 0
                setattr(obj, field, old_attr + int(cached_value))
        return actual_list

    def iterator(self):
        """
        Overwritten iterator which will apply the decorate functions before returning it.
        """
        base_iterator = super(IncrementalQuerySet, self).iterator()
        
        for fn in self._modify_funcs:
            base_iterator = fn(base_iterator)

        base_iterator = self.add_increments(base_iterator)
        
        for obj in base_iterator:
            for fn in self._decorate_funcs:
                fn(obj)

            yield obj

class IncrementalManager(models.Manager):
    def increment(self, id, field='', val=1):
        from django.db.models import F
        obj = self.model(pk=id)
        value = 0
        key = _key(obj, field)
        
        def atom_increment(pipe):
            key_val = pipe.get(key)
            value = int(key_val) if key_val is not None else 0
            value = value+val
            pipe.multi()
            if value>fluct or value<-fluct:
                pipe.set(key, 0)
                obj = obj.__class__.objects.get(pk=id)
                setattr(obj, field, getattr(obj, field)+value)
                obj.save()
            else:
                pipe.set(key, value)
        
        if settings.INCREMENTALS_FLUCTUATION is not None:
            fluct = settings.INCREMENTALS_FLUCTUATION
        else:
            fluct = 5
            
        settings.REDIS.transaction(atom_increment, key)
        
        return value

    def get_query_set(self):
        return IncrementalQuerySet(self.model)
    
